# Releasing Captura

Releases are built automatically for macOS, Windows, and Linux by GitHub
Actions and published to the Releases page. You only push a tag.

## One-time GitHub setup

1. Create a repository on GitHub (e.g. `captura`) and push this code (see below).
2. Nothing else — the workflow uses the built-in `GITHUB_TOKEN`, no secrets needed.

## First push

```sh
# from the project root (already a git repo with one commit)
git remote add origin https://github.com/catzuudon/captura.git
git push -u origin main
```

## Cutting a release

1. Bump the version in `app/__init__.py` (`__version__`) and add a section to
   `CHANGELOG.md`.
2. Commit, then tag and push the tag:

   ```sh
   git commit -am "Release 1.0.1"
   git tag v1.0.1
   git push origin main v1.0.1
   ```

3. The **Release** workflow (`.github/workflows/release.yml`) runs on the tag:
   it builds the macOS DMG, the Windows installer, and the Linux tarball, then
   creates a GitHub Release with all three attached and auto-generated notes.

The tag version (`v1.0.1` → `1.0.1`) becomes the filename/version on each
artifact. Keep `__version__` and the tag in sync.

## What gets built

| Platform | Artifact | Runner |
|----------|----------|--------|
| macOS    | `Captura-<v>-macos.dmg` (ad-hoc signed, `LSUIElement` tray app) | `macos-latest` |
| Windows  | `Captura-<v>-windows-setup.exe` (Inno Setup) | `windows-latest` |
| Linux    | `Captura-<v>-linux-x86_64.tar.gz` | `ubuntu-latest` |

## Checksums

Add SHA-256 checksums to the release notes so users can verify downloads
(the README documents how they verify). Generate them from the downloaded
artifacts:

```sh
shasum -a 256 Captura-*-macos.dmg Captura-*-linux-*.tar.gz
certutil -hashfile Captura-*-windows-setup.exe SHA256
```

## Signing (recommended before wide distribution)

Unsigned builds trigger Gatekeeper (macOS) and SmartScreen (Windows) warnings.
To remove them:

- **macOS**: an Apple Developer ID certificate (~$99/yr) + `codesign` +
  `notarytool` notarization + `stapler`. Replace the `codesign --force -s -`
  step in the workflow with your Developer ID identity and add a notarize step.
- **Windows**: an OV/EV code-signing certificate + `signtool` on the built
  `.exe` and installer.

Both require secrets (certificates) added to the repo's Actions secrets. Until
then, the README tells users how to bypass the warnings safely.

## First-release checklist

- [ ] `LICENSE` has your name
- [ ] `__version__` matches the tag
- [ ] `CHANGELOG.md` updated
- [ ] CI is green on `main`
- [ ] Pushed the tag; the Release workflow finished
- [ ] Added checksums to the release notes
