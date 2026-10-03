"""Scoped local filesystem primitives; no recursive repair, adoption or deletion."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import subprocess
import uuid

from .config import ROOT, ConfigError, logical_path, need
from .doctor import host_platform


def safe_path(path: Path) -> Path:
    logical_path(str(path), host_platform())
    need(path.is_absolute(), "An absolute local path is required")
    for entry in (path, *path.parents):
        need(not entry.is_symlink() and not (hasattr(entry, 'is_junction') and entry.is_junction()),
             "Symlink/junction paths require manual review")
        need(not (entry / '.git').exists(), "Private storage must be outside Git")
    resolved = path.resolve()
    need(not resolved.is_relative_to(ROOT) and not ROOT.is_relative_to(resolved), "Repository storage is forbidden")
    if os.name != 'nt' and len(path.parts) >= 3 and path.parts[1] in ('mnt', 'Volumes'):
        need(Path(*path.parts[:3]).is_mount(), "Requested external filesystem is not mounted")
    return resolved


def windows_acl(path: Path, *, create: bool = False) -> None:
    # Pass the path as JSON on stdin, never interpolate it into PowerShell source.
    script = r'''
$ErrorActionPreference = 'Stop'
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
$target = $request.path
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
if ($request.create) {
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetOwner($sid)
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($value in @($sid.Value, 'S-1-5-18', 'S-1-5-32-544') | Select-Object -Unique) {
        $principal = [Security.Principal.SecurityIdentifier]::new($value)
        $rule = [Security.AccessControl.FileSystemAccessRule]::new($principal, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    [IO.Directory]::SetAccessControl($target, $acl)
}
$sections = [Security.AccessControl.AccessControlSections]::Access -bor [Security.AccessControl.AccessControlSections]::Owner
$actual = if ([IO.Directory]::Exists($target)) { [IO.Directory]::GetAccessControl($target, $sections) } else { [IO.File]::GetAccessControl($target, $sections) }
$owner = $actual.GetOwner([Security.Principal.SecurityIdentifier]).Value
if ($owner -ne $sid.Value) { throw 'Unexpected owner' }
$rules = @($actual.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
if ($rules.Count -eq 0) { throw 'Empty ACL' }
$ownRule = $false
foreach ($rule in $rules) {
    if ($rule.IdentityReference.Value -notin @($sid.Value, 'S-1-5-18', 'S-1-5-32-544')) { throw 'Unapproved principal' }
    if ($rule.AccessControlType -ne 'Allow') { throw 'Unexpected deny rule' }
    if ($rule.IdentityReference.Value -eq $sid.Value -and ($rule.FileSystemRights -band [Security.AccessControl.FileSystemRights]::FullControl) -eq [Security.AccessControl.FileSystemRights]::FullControl) { $ownRule = $true }
}
if (-not $ownRule) { throw 'Owner access missing' }
[Console]::Write('acl-ok')
'''
    try:
        environment = os.environ.copy()
        environment.pop('PSModulePath', None)  # Do not load PowerShell 7 modules into Windows PowerShell.
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                                input=json.dumps({'path': str(path), 'create': create}), capture_output=True,
                                text=True, timeout=15, shell=False, env=environment)
        need(result.returncode == 0 and result.stdout == 'acl-ok', "Private ACL verification failed; no permission repair attempted")
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ConfigError("Private ACL adapter unavailable; no automatic elevation") from error


def verify_private(path: Path, *, directory: bool = False) -> None:
    safe_path(path)
    info = path.stat()
    need(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode), "Unexpected private resource type")
    if not directory:
        need(info.st_nlink == 1, "Hard-linked state requires manual review")
    if os.name == 'nt':
        windows_acl(path)
    else:
        need(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600),
             "Private owner/mode verification failed; no permission repair attempted")


def create_private_directory(path: Path) -> None:
    safe_path(path)
    need(path.parent.is_dir(), "Storage parent must already exist")
    path.mkdir(mode=0o700)  # Exclusive; never chmod an existing directory.
    if os.name == 'nt':
        windows_acl(path, create=True)
    verify_private(path, directory=True)


def sync_directory(path: Path) -> None:
    if os.name != 'nt':
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic_json(path: Path, value: dict, *, replace: bool = False) -> None:
    """Publish complete JSON. Only replace an already verified owned state snapshot."""
    safe_path(path)
    verify_private(path.parent, directory=True)
    if replace:
        verify_private(path)
    else:
        need(not path.exists(), "Refusing to overwrite an existing private artifact")
    temporary = path.parent / ('.pending-' + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    # Inherit the protected parent ACL. No secret appears before root hardening.
    verify_private(temporary)
    if replace:
        os.replace(temporary, path)
    else:
        os.link(temporary, path)  # Atomic no-clobber publication, including Windows NTFS.
        temporary.unlink()  # Only this function's exact, newly created temporary file.
    sync_directory(path.parent)


def read_private(path: Path) -> dict:
    from .config import load_json
    verify_private(path)
    value = load_json(path)
    need(isinstance(value, dict), "Private artifact must be an object")
    return value


def create_lock_file(path: Path) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(b'0')
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def operation_lock(path: Path):
    verify_private(path)
    stream = path.open('r+b')
    locked = False
    try:
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as error:
            raise ConfigError("Another operation holds this installation lock; retry after it finishes") from error
        yield
    finally:
        if locked:
            if os.name == 'nt':
                import msvcrt
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()
