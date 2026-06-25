# MSI Build Recipe — Exact WXS + .idt + commands

Verified working with wixl 0.106 on Debian/Ubuntu. Build a minimal file-drop MSI then inject certutil custom actions via msibuild .idt import.

## Prerequisites
```bash
apt-get update && dpkg --configure -a && apt-get install -y msitools wixl
```

## Step 1 — Minimal file-drop WXS
Save as `cert.wxs`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
  <Product Id="*"
           Name="[Cert Name] Root Certificate ([CN])"
           Language="1033"
           Version="1.0.0.0"
           Manufacturer="[Organization]"
           UpgradeCode="[GUID]">

    <Package InstallerVersion="200"
             Compressed="yes"
             InstallScope="perMachine"
             Description="Installs the [CN] certificate into the Windows Trusted Root store" />

    <MajorUpgrade DowngradeErrorMessage="A newer version is already installed." />
    <Media Id="1" Cabinet="cab1.cab" EmbedCab="yes" />

    <Directory Id="TARGETDIR" Name="SourceDir">
      <Directory Id="ProgramFilesFolder">
        <Directory Id="INSTALLFOLDER" Name="[Folder Name]">
          <Component Id="CertFile" Guid="[GUID2]">
            <File Id="cert.cer" Name="[filename].cer" Source="[filename].cer" KeyPath="yes" />
          </Component>
        </Directory>
      </Directory>
    </Directory>

    <Feature Id="MainFeature" Title="[Cert Name] Certificate" Level="1">
      <ComponentRef Id="CertFile" />
    </Feature>
  </Product>
</Wix>
```

## Step 2 — Build the base MSI
```bash
wixl cert.wxs -o Certificate.msi
```

## Step 3 — Verify and inject custom actions
The base MSI only drops the `.cer` file. Inject certutil via `.idt` import:

### CustomAction.idt (use actual TAB separators, CRLF line endings)
```
Action	Type	Source	Target	ExtendedType
s72	i2	S72	S255	I4
CustomAction	Action
AddCert	3106	INSTALLFOLDER	certutil.exe -addstore -f Root [filename].cer	
DelCert	3170	INSTALLFOLDER	certutil.exe -delstore Root [CN]	
```

### InstallExecuteSequence.idt — export base, append rows
```bash
msiinfo export Certificate.msi InstallExecuteSequence | tr -d '\r' > ies_base.txt
sed -i '/^[[:space:]]*$/d' ies_base.txt
printf 'AddCert\tNOT Installed\t4100\nDelCert\tREMOVE="ALL"\t3400\n' >> ies_base.txt
sed 's/$/\r/' ies_base.txt > InstallExecuteSequence.idt
```

### Import
```bash
msibuild Certificate.msi -i CustomAction.idt
msibuild Certificate.msi -i InstallExecuteSequence.idt
```

## Step 4 — Verify the tables
```bash
msiinfo export Certificate.msi CustomAction          # must show AddCert + DelCert
msiinfo export Certificate.msi InstallExecuteSequence | grep -iE "AddCert|InstallFiles|RemoveFiles"
```
AddCert must be at sequence 4100 (after InstallFiles at 4000). DelCert at 3400 (before RemoveFiles at 3500).

## Type bit encoding
| Bit | Value | Meaning |
|-----|-------|---------|
| Exe | 2 | Source is an executable |
| Directory source | 32 | Source field = directory property |
| Deferred (in-script) | 1024 | Runs during install script |
| No impersonate | 2048 | Runs as LocalSystem (elevated) |
| Continue (ignore return) | 64 | Don't fail install if action fails |

- **3106** = 2+32+1024+2048 → deferred, elevated, directory-EXE, checks return
- **3170** = 3106+64 → same but resilient (the uninstall delete shouldn't break if cert already gone)

## CRLF pitfall
`msiinfo export` emits CRLF. If you add another `sed 's/$/\r/'` without stripping first, lines get `^M^M` and the .idt import silently corrupts the tables. Always `tr -d '\r'` first, then re-add `sed 's/$/\r/'`.
