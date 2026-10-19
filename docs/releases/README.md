# Releases and versioning

Each published version maps to one immutable Git tag and one GitHub release created from the same reviewed commit.

## Version policy

| Change | Version example | Release type |
| --- | --- | --- |
| Early bounded phase work | `0.5.0-alpha.1` | Prerelease |
| Integrated phase candidate | `0.5.0-rc.1` | Prerelease |
| Completed milestone | `0.5.0` | Stable release |
| Compatible fix or documentation update | `0.5.1` | Patch release |
| Backward-compatible feature set | `0.6.0` | Minor release |
| Incompatible public behavior after 1.0 | `2.0.0` | Major release |

Never reuse a version or move an existing tag. If a published release needs correction, prepare and publish the next version.

## Release checklist

1. Finish the phase's declared implementation, documentation and recovery evidence.
2. Update `CHANGELOG.md`, package/catalog versions, support matrix and release notes.
3. Review and stage only the intended files.
4. Run repository, phase-specific, publication, complete regression and whitespace checks.
5. Commit with a concise product-focused subject and push the exact commit.
6. Require the full GitHub Actions matrix to pass.
7. Create an annotated tag and matching GitHub release from that commit; mark alpha/RC versions as prereleases.
8. Start the next update from a clean synchronized branch.

## Published notes

- [0.1.0](v0.1.0.md) — repository foundation
- [0.2.0](v0.2.0.md) — configuration discovery
- [0.3.0](v0.3.0.md) — planning and host doctor
- [0.4.0](v0.4.0.md) — safe execution primitives
- [0.5.0-alpha.1](v0.5.0-alpha.1.md) — isolated Glance starter
- [0.5.0-alpha.2](v0.5.0-alpha.2.md) — isolated Uptime Kuma
- [0.5.0-rc.1](v0.5.0-rc.1.md) — integrated Phase 4 candidate
- [0.6.0-alpha.1](v0.6.0-alpha.1.md) — Paperless-ngx application-aware recovery candidate
- [0.6.0-alpha.2](v0.6.0-alpha.2.md) — Paperless-ngx encrypted recovery vault candidate
