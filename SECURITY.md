# Security Policy

## Reporting a vulnerability

Please report security issues **privately** so they can be fixed before public
disclosure:

- Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  (Security tab → "Report a vulnerability"), or
- Open a minimal public issue asking for a private contact channel — without
  details.

Please don't file public issues with exploit details.

## Scope and design

Captura is a local desktop application:

- **No network access.** It does not connect to the internet, upload captures,
  or send telemetry.
- **No shell execution**, no `eval`/`exec`, no deserialization of untrusted
  data (`pickle`/`yaml`/etc.).
- OCR runs the local Tesseract binary; the OCR language string is validated
  before it reaches Tesseract's command line.
- Settings are read from the user config directory and are type-validated on
  load, so a corrupted or tampered file falls back to safe defaults.
- The macOS login-item plist is XML-escaped.

## Trust model

- Captura runs whatever `tesseract` binary it finds (PATH first, then standard
  install locations). As with any tool that calls a system binary, only install
  Tesseract from a trusted source.
- Release binaries are **unsigned** (no paid signing certificate). Verify the
  SHA-256 checksum on the release page before running, and prefer building from
  source if you require a verified provenance.

## Supported versions

Security fixes target the latest release. Dependencies are pinned in
`requirements.txt`; review advisories (notably for Pillow and PyQt6) before
upgrading.
