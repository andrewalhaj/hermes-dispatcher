# macOS .mobileconfig Template — Certificate Trust Profile

Save as `Certificate.mobileconfig`. Replace all `[PLACEHOLDER]` values.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>PayloadCertificateFileName</key>
            <string>[filename].cer</string>
            <key>PayloadContent</key>
            <data>
[BASE64-DER-WRAPPED-AT-60-COLS]
</data>
            <key>PayloadDescription</key>
            <string>Installs and trusts the [CN] root certificate.</string>
            <key>PayloadDisplayName</key>
            <string>[Cert Name] ([CN])</string>
            <key>PayloadIdentifier</key>
            <string>[reverse-dns-identifier]</string>
            <key>PayloadType</key>
            <string>com.apple.security.root</string>
            <key>PayloadUUID</key>
            <string>[UUID]</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
        </dict>
    </array>
    <key>PayloadDescription</key>
    <string>Installs the [CN] self-signed certificate into the System keychain as a trusted root.</string>
    <key>PayloadDisplayName</key>
    <string>[Cert Name] ([CN])</string>
    <key>PayloadIdentifier</key>
    <string>[reverse-dns-identifier-top]</string>
    <key>PayloadOrganization</key>
    <string>[Organization]</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadScope</key>
    <string>System</string>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>[UUID-TOP]</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>
```

## Build steps
```bash
# 1. Generate UUIDs
python3 -c "import uuid; print('PROFILE='+str(uuid.uuid4()).upper()); print('PAYLOAD='+str(uuid.uuid4()).upper())"

# 2. Base64-encode the DER cert, wrap at 60 columns
base64 -w0 cert.cer > cert.b64
fold -w 60 cert.b64 > cert_wrapped.b64

# 3. Insert the wrapped base64 into the PayloadContent > data block
#    (indent 12 spaces to match the XML nesting)

# 4. Replace all placeholders, save as .mobileconfig
```

## Verify before handing off
```bash
# The embedded cert must round-trip byte-identical to the source
python3 -c "
import plistlib, subprocess
d = plistlib.load(open('Certificate.mobileconfig', 'rb'))
c = d['PayloadContent'][0]['PayloadContent']
open('/tmp/rt.der', 'wb').write(c)
subprocess.run(['openssl', 'x509', '-inform', 'der', '-in', '/tmp/rt.der', '-noout', '-subject', '-fingerprint', '-sha256'])
"
# Compare SHA-256 against: openssl x509 -inform der -in cert.cer -noout -fingerprint -sha256
```

## User-facing caveats
- **Manual install ≠ auto-trusted.** Self-signed roots installed by double-click require the user to open Keychain Access → find the cert → Trust → "Always Trust."
- **MDM-pushed profiles are trusted automatically.** Deploy via Jamf/Intune/Kandji for zero-touch fleet rollout.
- **macOS marks the profile "Unverified"** since the .mobileconfig itself isn't signed. Fine for managed deploy.
