---
name: certificate-installer-packaging
description: "Build cross-platform cert trust-store installers."
---

# Certificate Installer Packaging

Build double-clickable certificate installers from a raw cert file, on a Linux box, without touching the target machines. Covers Windows (MSI), macOS (.mobileconfig), and format conversion. An MSI is **Windows-only** — a mixed Mac+Windows fleet needs two separate artifacts.

## When to use
- "Install this cert onto our computers / Macs / Windows machines."
- "Make an MSI / installer for this certificate."
- Convert/inspect a `.cer`/`.der`/`.pem`/`.crt` and package it for trust.

## Step 0 — Inspect & convert the cert FIRST
A `.cer` may be **DER (binary)** or **PEM (text)**. Always identify and normalize before packaging.

```bash
# DER->PEM (most .cer from Windows are DER). If already PEM this errors; then use -inform pem.
openssl x509 -inform der -in cert.cer -out cert.pem 2>&1 && echo "was DER" || \
  openssl x509 -inform pem -in cert.cer -out cert.pem
# Identity + fingerprints (run each flag in its own call — openssl rejects -sha1 AND -sha256 together)
openssl x509 -in cert.pem -noout -subject -issuer
openssl x509 -in cert.pem -noout -fingerprint -sha256
```
Note for the user: **issuer == subject ⇒ self-signed**. `CA:FALSE` + EKU serverAuth ⇒ it's a leaf **server cert, not a CA** — installing as trusted root pins trust of that exact cert but it can't sign others. A bare cert file is **public-only (no private key)** — it makes a machine *trust* the host, it does NOT let the machine *serve* as that host.

## Windows MSI
Toolchain on Debian/Ubuntu: `apt-get install -y msitools wixl` (gives `wixl`, `msibuild`, `msiinfo`).

**Approach:** build a minimal file-drop MSI with `wixl`, then inject the `certutil` custom actions via `msibuild` `.idt` import. Do NOT rely on wixl `<CustomAction>` for elevated directory-EXE actions — see pitfall.

Install action: `certutil.exe -addstore -f Root cert.cer` (machine Trusted Root). Uninstall: `certutil.exe -delstore Root <CN>`.

See `references/msi-build-recipe.md` for the full WXS + .idt files and exact command sequence (verified working with wixl 0.106).

Silent deploy for GPO/Intune: `msiexec /i Cert.msi /qn` (elevated).

## macOS .mobileconfig
A configuration profile is the Mac equivalent of the MSI for cert trust (cleaner than a `.pkg`, and it's what MDM pushes).

- Embed the cert as base64 **DER** (wrap at 60 cols) inside a `com.apple.security.root` payload.
- `PayloadScope` = `System`, outer `PayloadType` = `Configuration`.
- Double-click → System Settings → Profiles → Install.
- **Manual install ≠ auto-trusted:** for a self-signed root the user may still need Keychain Access → "Always Trust". **MDM-pushed** profiles ARE trusted automatically. Tell the user this.

See `references/mobileconfig-template.md` for the full plist template + the verification that the embedded base64 round-trips byte-identical to the source cert.

## Verification (do before handing files over)
- MSI: `msiinfo export Cert.msi CustomAction` shows your AddCert/DelCert rows; `msiinfo export Cert.msi InstallExecuteSequence | grep -iE "AddCert|InstallFiles"` confirms AddCert is sequenced right after `InstallFiles`.
- mobileconfig: load with `python3 -c "import plistlib; ..."` and confirm the decoded payload's SHA-256 matches the source cert's SHA-256 (proves the embed is intact).

## Pitfalls
- **wixl 0.106 silently drops `<CustomAction>` with `Directory=`** — emits `GLib-GObject-CRITICAL ... has no property named 'Directory'` and `Source != NULL` assertions, but STILL writes an MSI. That MSI only drops the file; it never runs certutil. Fix: inject custom actions via `msibuild -i CustomAction.idt`. Always verify the CustomAction table post-build.
- **CustomAction Type encoding:** `3106` = exe(2)+dir-source(32)+deferred/in-script(1024)+no-impersonate(2048) → runs elevated (LocalSystem) against the **machine** Root store. Add `+64` (=3170) for "ignore return code" on the uninstall delete.
- **.idt format is strict:** tab-separated, **CRLF** line endings, 3-line header (names / types / "TableName\tKeyCol"). `msiinfo export` already emits CR — strip with `tr -d '\r'` before re-adding `sed 's/$/\r/'`, or you get doubled `^M^M` and the import corrupts.
- **openssl fingerprint flags are mutually exclusive** in one call (`-sha1 -sha256` errors "Multiple digest"). One flag per invocation.
- **MSI/profile are unsigned** — Windows SmartScreen warns; macOS marks profile "Unverified". Fine for managed deploy (GPO/MDM trust it); flag to the user for manual double-click installs.
- The deliverable is **two files** for a mixed fleet. Don't hand someone an MSI for their Macs.
