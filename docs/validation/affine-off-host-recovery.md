# AFFiNE browser and off-host clean-runner recovery gate

Version: **0.6.0-alpha.5**

Scope: generated non-personal workspace and note only; no household AFFiNE users, notes, credentials, files or database rows

Decision: **Go for the bounded experimental recovery gate after both clean-runner jobs pass on the exact release commit. No-go for production adoption or backup replacement.**

## Windows browser and independent-restore proof

On 2026-10-21 a disposable Windows Docker Desktop trial completed one coherent source-to-recovery sequence:

- initialized a fresh digest-pinned AFFiNE 0.27.4 project;
- signed in through a digest-pinned Playwright 1.64.0 Chromium runtime;
- created a synced workspace and rendered synthetic title/paragraph;
- verified reload persistence and a second independent browser context;
- verified separate server-sync state and source application restart;
- quiesced AFFiNE and captured PostgreSQL custom dump, config, storage, private recovery inputs and browser evidence;
- restored into unrelated containers, volumes, credentials, root and port;
- rendered the recovered note through independent browser sessions;
- stopped and started the recovered project and repeated content/browser verification.

Sanitized proof:

```text
proof kind:                  homelab-affine-local-browser-recovery-proof
browser rendered:            true
independent browser sessions:true
reload persistence:          true
application-consistent:      true
independent restore:         true
restart persistence:         true
production data used:        false
title SHA-256:               49ea565c3483aa641d622b05831de1ca2b7cbdf88afb4a5f5e332961b9ca151c
body SHA-256:                283a5333e9acf1f57aa618e8a5c6de3a955e7414888784319c2f177881a3caec
proof ID:                    2953f601b4a6546d341ff80a49a80d4724ffa3b8a254f41ad8448cc065630d00
```

The validator remained read-only except for its own synthetic workspace. Its temporary browser had no Docker socket, used an unprivileged user, a read-only root, dropped capabilities, bounded resources and a dedicated frontend network. Evidence was streamed into the private installation tree without relaxing its ACL. All disposable trial containers, networks and volumes were removed afterward.

## Required clean-runner evidence

The manually dispatched `AFFiNE off-host recovery rehearsal` workflow is the authoritative Linux amd64 portability gate:

1. **Prepare encrypted off-host artifact** creates synthetic AFFiNE content, performs browser and restart checks, makes an application-consistent backup, stores it in a new encrypted Restic repository, reads every repository data pack, locally decrypts it and uploads only the encrypted repository plus nonsecret portable manifest.
2. **Recover on independent clean runner** downloads that immutable artifact on a new hosted runner, receives `AFFINE_DR_TEST_PASSWORD` separately from the repository secret, independently verifies Restic, checks all data packs, decrypts the exact snapshot, restores a fresh AFFiNE project and repeats browser rendering plus stop/start persistence.

Artifact upload/download actions and the browser/application images are immutable digest or commit references. The encrypted repository expires after seven days; sanitized proof expires after thirty days.

## Pass criteria

- source and recovery use separate fresh hosted runners;
- transferred content excludes operational/recovery keys and plaintext backup;
- Restic archive/executable checksums match reviewed Linux amd64 values;
- repository, snapshot, AFFiNE manifest and browser fingerprints match;
- full repository data check precedes decryption;
- the fresh application renders the expected nonempty synthetic note and survives stop/start;
- proof identifies the exact source commit and immutable artifact digest;
- the Windows host and production AFFiNE deployment are never contacted.

## Boundary

Passing proves the synthetic repository format, portable manifest, separately injected key and clean-runner application/browser recovery process. It does not provide durable production storage, migrate personal notes, prove the user's real offline key, test native clients/attachments/multi-user load, set recovery objectives or replace the current production schedule.
