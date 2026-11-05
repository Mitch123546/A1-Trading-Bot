# Security and operational safety

## Secrets

- Store Alpaca paper keys, the dashboard password, the session-signing secret, and the optional
  Discord webhook only in `.env`.
- `.env` is gitignored. Never put secrets in issues, screenshots, chat messages, or commits.
- Rotate a key immediately if it is exposed.
- Use keys belonging to a dedicated paper account for this phase.

## Network exposure

The app uses a signed, HTTP-only, same-site cookie, but local development uses plain HTTP. It is
appropriate for localhost or a trusted home LAN. It is not hardened for direct internet exposure.
Do not configure router port forwarding. A future hosted version must add HTTPS, a managed identity
provider, CSRF review, rate limiting, centralized secret storage, backups, and monitoring.

## Trading safety

This repository contains no live broker endpoint. Adding live execution is a separate future change
requiring code review, broker-side protective orders, a read-only soak period, reconciliation,
idempotency testing, manual approvals, and much smaller initial capital.

Report security problems privately to the repository owner rather than opening a public issue that
contains exploit details or secrets.

