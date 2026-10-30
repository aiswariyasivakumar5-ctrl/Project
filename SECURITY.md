# Security policy

## Reporting a vulnerability

Please report security issues privately to the maintainers through the
repository's GitHub Security Advisories feature. Include the affected version,
deployment mode, steps to reproduce, and any relevant sanitized logs. Do not
include live credentials, customer data, or unredacted tool arguments. The
maintainers will acknowledge reports and coordinate a fix and disclosure
timeline with the reporter.

If private reporting is unavailable, contact the repository owner directly
through a verified maintainer address listed on the project profile. Do not
open a public issue for an unpatched vulnerability.

## Deployment responsibilities

Use TLS for non-loopback access, keep client and operator credentials separate,
protect state and audit files, and grant tool permissions explicitly. Sentinel
withholds some responses only after an upstream tool has executed; it does not
provide process isolation or undo external side effects. See
[`docs/production_gaps.md`](docs/production_gaps.md) for current limitations.
