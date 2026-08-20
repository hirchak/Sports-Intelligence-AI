# Security

Status: M0 baseline. Full security pass scheduled as part of M10.

## Requirements (from master spec §34) and current state

| Requirement                                  | M0 state                                                       |
|----------------------------------------------|----------------------------------------------------------------|
| Telegram allowlist                           | Config field `TELEGRAM_ALLOWED_USER_IDS` ready; bot in M3      |
| No secrets in Git                            | `.env` ignored; `.env.example` placeholders only               |
| Non-root container users                     | API image runs as `appuser` (uid 10001) in production target   |
| Database/Redis not public                    | Host ports bound to 127.0.0.1 only; production: internal net   |
| Dependency versions locked                   | `uv.lock` committed; CI installs `--frozen`                    |
| Production debug mode disabled               | N/A locally; revisit in M10                                    |
| Principle of least privilege                 | Separate compose project/volumes (ADR-0003)                    |
| No arbitrary shell commands from Telegram    | By design (M3)                                                 |
| Sensitive headers redacted in logs           | JSON logging only; provider adapters in M2+ must follow        |

## Secrets policy

- Never commit `.env`, API keys, tokens, SSH credentials.
- If a secret is accidentally committed: flag immediately and rotate —
  even if the commit is later deleted (`16_GITHUB_AI_DEVELOPMENT_CONTROL.md` §9).
- Secret scan before every push: `git diff` review + pattern check.
