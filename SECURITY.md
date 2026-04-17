# Security Policy

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Instead, use GitHub's private vulnerability reporting:
👉 [Report a vulnerability](https://github.com/compactbench/compactbench/security/advisories/new)

This creates a private advisory only maintainers can see.

### What to expect

- Acknowledgement within **3 business days**
- Substantive response within **14 days**
- Credit in the fix commit and public advisory (unless you ask us not to)

### What counts as a vulnerability

In scope:

- Vulnerabilities in the `compactbench` Python package (`src/compactbench/`)
- Vulnerabilities in the leaderboard runner infrastructure
- Any leak vector that lets a submitter view hidden ranked templates
- Supply-chain risks specific to our release pipeline

Out of scope:

- Denial-of-service via oversized submissions — the runner enforces rate and size limits
- Social-engineering of maintainers
- Dependency vulnerabilities — please report upstream first; we track fixes via Dependabot

## Supported versions

CompactBench is pre-1.0. Only the **latest release** on PyPI receives security fixes.

| Version | Supported |
|---|---|
| Latest release | ✅ |
| Anything older | ❌ |

## Commitments

CompactBench is maintained by a small volunteer group:

- We **will** triage every credible report and fix real issues.
- We **cannot** offer bug bounties or guaranteed response SLAs.
- We **cannot** guarantee response times during holidays or long weekends.

## Safe harbor

We will not pursue legal action against researchers who:

- Report in good faith through the channel above.
- Do not exfiltrate more data than necessary to demonstrate the issue.
- Do not disclose publicly until we have issued a fix or 90 days have passed, whichever comes first.
