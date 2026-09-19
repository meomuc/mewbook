# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Report it privately to
**[project owner: fill in a private contact address, or enable the host's private vulnerability reporting, before publishing]**.

Include: what you found, how to reproduce it, the MewBook version (*Help → About*), and what you think the impact is. Please
don't include real user data. We will acknowledge a report within a week, work on a fix, and credit you in the release notes
unless you prefer not to be named. MewBook is maintained by volunteers: there is no bug bounty and no fixed fix-time promise.

## Supported versions

Only the latest release receives fixes.

## What is in scope

MewBook is a desktop application that runs on your computer and keeps your library on your computer. Relevant areas:

- **Handling of untrusted files:** opening, indexing or converting a crafted PDF, EPUB, MOBI or image (crashes, memory
  corruption, path traversal, writing outside the intended folder).
- **Secrets on disk:** API keys are stored encrypted in `settings.json` with a key in `.secret.key` next to it. That protects
  against casual exposure of the settings file, **not** against someone who can read both files (`core/secret_store.py`
  says so). Reports that a local attacker with full access to your profile can read the keys are known and out of scope.
- **The review service client:** how the app talks to a Supabase project you configure. The Supabase "anon" key is public by
  design; access control is Row Level Security plus the `submit_review` function
  (`src/smartdoc/application/sql/001_reviewer_identity.sql`). Server-side problems in a specific Supabase project belong to
  whoever runs that project.
- **The installer and the update path:** MewBook has no auto-updater yet. Releases publish SHA-256 checksums
  (`SHA256SUMS.txt`); the installer is not code-signed until a certificate is in place, which Windows SmartScreen reports.

## What is out of scope

- Findings that need a modified or malicious build of MewBook.
- Denial of service by importing enormous files into your own library.
- Vulnerabilities in third-party services MewBook can call (cover sources, AI providers) or in libraries it bundles: report
  those upstream (we will update the dependency once a fix exists; see `THIRD_PARTY_NOTICES.md`).

## Privacy in issue reports

The "support info" text from *Help → About* is designed to be safe to paste publicly (no book titles, no keys, no Windows account
name). Never attach your library, `settings.json`, `identity.dat` or `.secret.key`.
