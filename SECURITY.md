# Security Policy

## Intended use

RedScribe is a note-taking application for authorized security work: CTF
competitions, lab environments, and engagements where you have explicit,
written permission to test. The built-in command snippets are reference
material, not permission to attack a system.

## Data handling

- RedScribe is local-first. The vault is a single SQLite database on your
  machine, and the app contains no telemetry, analytics, or background network
  calls.
- The only network interaction is a link you explicitly click in a preview.
  RedScribe opens `http`, `https`, and `mailto` links in your default browser.
- Notes are stored unencrypted. Use full-disk encryption and your operating
  system's account protection for sensitive engagement data.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Report it privately
through GitHub Security Advisories on the repository. Include the affected
version, a reproduction, and the impact. You can expect an acknowledgement
within 72 hours.
