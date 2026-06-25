---
name: t2-mac-linux-install
description: "Install Linux on T2 Intel Macs (2018-2020): t2linux flow."
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [t2linux, mac-mini, ubuntu, install, boot, efi, broadcom]
    related_skills: [hermes-maintenance]
    created_by: agent
load_when:
  - "installing Linux/Ubuntu on an Intel Mac (2018-2020, T2 chip)"
  - "Mac boot picker / Startup Security / EFI boot from USB problems"
  - "migrating Hermes to a Mac mini"
---

# Linux on T2 Intel Macs (2018 Mac mini proven flow, 2026-06)

Standard Ubuntu ISOs DON'T boot on T2 Macs — use t2linux patched builds. Live walkthrough with Andrew's 2018 mini; pitfalls below each cost a real round-trip.

## Sequence

1. **Keep macOS partitioned, don't wipe.** Broadcom Wi-Fi firmware is legally extractable only from macOS; also serves as rollback. Headless-on-Ethernet servers can skip Wi-Fi but extract anyway.
2. **Firmware extraction (on macOS):**
   ```bash
   curl -sLo firmware.sh https://wiki.t2linux.org/tools/firmware.sh
   bash firmware.sh        # pick Method 1 (copies to EFI partition)
   ```
   ⚠️ **NEVER `curl | bash` this script** — it's interactive; piping makes its menu read garbage → "invalid option". Download-then-run.
   - sudo prompt for "mounting EFI partition" is normal (diskutil mount); password typed blind.
3. **Partition** free space in Disk Utility (any FS; installer reformats).
4. **Startup Security** (Recovery → Utilities → Startup Security Utility): Secure Boot = **No Security** AND **Allow booting from external media**. The external-boot checkbox is the gate — USB is silently invisible in the boot picker without it.
5. **ISO:** github.com/t2linux/T2-Ubuntu releases. ISOs are **split into .iso.00–.03 parts** (GitHub size cap). Use the release's `iso.sh` to download+join, or `cat name.iso.0* > name.iso`. Flashing a single `.00` part = unbootable stick (presents as "EFI Boot didn't see USB"). Pick plain ubuntu-LTS for servers, not desktop flavors.
6. **Flash** with Etcher (let verify pass run). **Boot:** full shutdown → hold Option until picker → "EFI Boot".
7. **Post-install:** run firmware.sh again inside Ubuntu (retrieves from EFI), reboot → Wi-Fi/BT live.
   - ⚠️ **Method 1 only works if the macOS ESP survived.** If the installer erased the disk (or made its own ESP), the firmware stash is gone — Method 1 fails with `tar: firmware-raw.tar.gz: Cannot open`. Fallback: **Method 3** (downloads Apple's Sonoma recovery image, ~753MB) works standalone with no macOS needed. It requires `dmg2img` (`apt install dmg2img`) first. The "Image verification failed (Inappropriate ioctl)" warning over SSH is cosmetic — extraction proceeds fine. Drivers reload live, no reboot needed; verify with `nmcli dev wifi list` + `bluetoothctl list`.
   - Script is interactive over SSH too: feed answers via `printf "3\n7\n" | sudo bash firmware.sh` (method, then macOS version — 7=Sonoma).
   - ⚠️ **"Install alongside macOS" can silently not happen** — verify post-install with `lsblk`: if the disk shows only EFI+ext4 and no APFS container, macOS was erased and the dual-boot rollback assumption is dead. Check before telling the user macOS is still there.

## Windows keyboard on a Mac

- Option = **Alt**; Command = **Win key**. Recovery = Win+R at power-on, boot picker = hold Alt.
- Keys must be held BEFORE power-on, from full shutdown, wired keyboard in a **rear USB-A port** (no hub; BT keyboards don't register at firmware time).
- **If keystrokes don't register at firmware time** (boots straight to login): skip the timing game —
  ```bash
  sudo nvram "recovery-boot-mode=unused" && sudo reboot   # one-shot boot into Recovery
  ```
  Deterministic; flag self-clears.

## "USB not in boot picker" triage (ranked)

1. External boot still blocked (step 4 incomplete/partially applied — T2 sometimes takes Secure Boot but not the external checkbox; re-verify both).
2. Flashed a split part instead of the joined ISO (file must be GB-scale `.iso`, no `.0N` suffix).
3. Front/hub/USB-C ports or a stick that doesn't enumerate at firmware time → rear USB-A, second stick.
4. Bad flash → re-flash with verify.
Diagnostic question that splits 1 vs 2-4: did the picker show ONLY Macintosh HD (stick invisible → 1/2/3) or nothing at all (display/timing)?

## Live USB ≠ installed system (cost a full session, 2026-06-12)

Booting "EFI Boot" lands in the **live session** — it looks fully functional (desktop, apt, network) but runs entirely in RAM. Nothing persists. Real failure: user did apt/curl/firmware work in the live session believing Ubuntu was installed; reboot landed in macOS, all work gone.

- **Detection:** reboot drops into macOS + macOS `diskutil list` shows one full-disk APFS container and no Linux partition → installer never ran. Live-session username is `ubuntu`; an installed system uses the name created during install.
- **Installer icon may be missing from the live desktop.** Search "install" via Activities, or launch from terminal: `sudo ubiquity` (22.04) / `sudo ubuntu-desktop-bootstrap` (24.04 noble).
- At the disk step choose **"Install alongside macOS"** (shrinks APFS) — never "Erase disk" (kills the Wi-Fi-firmware source + rollback).
- **firmware.sh's Linux-side run must happen on the INSTALLED system.** Running it in the live session doesn't persist. macOS-side stash to EFI survives; the Ubuntu-side retrieval must be redone post-install.
- Quirk seen in live session only: PATH lost `/usr/bin` etc. (`sudo`/`curl` "not found"); fix `export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`. Not seen on installed system.

## Post-install: remote agent control (proven flow)

1. On the mini: `sudo apt install -y openssh-server`, then `curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up` (auth URL → approve).
2. From the agent box: `tailscale status` to get the node IP, append agent pubkey to `~/.ssh/authorized_keys` **of the installed user** (not `ubuntu` — that's the live-session user; wrong user = `Permission denied (publickey,password)`).
3. Verify: `ssh <user>@<ts-ip> 'whoami && uname -r'` — kernel should read like `7.0.12-1-t2-noble`.
4. Remote sudo over non-tty SSH fails (`a terminal is required`); interactive steps need the user at the keyboard or a NOPASSWD sudoers drop-in.

## ⚠️ Live-USB session ≠ installed system (cost a full session, 2026-06-12)

The live desktop boots into a fully working Ubuntu that LOOKS installed — apt works, packages install, firmware.sh runs. **All of it is RAM-only and evaporates on reboot.** Symptoms of having been in a live session all along: reboot lands back in macOS, `diskutil list` (macOS) / `lsblk` (Linux) shows NO Linux partition, and every package/config you set up is gone.

- **Verify install-to-disk happened BEFORE doing any setup work:** `lsblk` must show an ext4 root partition on the internal disk. If the disk is still one APFS container, the installer never ran.
- The "Install Ubuntu" icon can be missing from the live desktop. Launch via Activities search → "install", or terminal: `sudo ubiquity` (22.04) / `sudo ubuntu-desktop-bootstrap` (24.04).
- Live-session quirks that look like system breakage but aren't worth fixing: PATH can lose /usr/bin (sudo/curl "not found" — `export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`), and the live user is `ubuntu` while the installed system uses whatever username was chosen — don't install SSH keys or assume usernames until you've confirmed you're on the installed system.
- After real install, T2 Macs may still default-boot macOS: System Preferences → Startup Disk, or `sudo bless --device /dev/diskXsY --setBoot` from macOS, or hold Alt each boot.

## Misconceptions to head off

- **Live USB session masquerades as an installed system (PROVEN 2026-06-12).** Booting "EFI Boot" lands in a fully working desktop — user can apt install, run firmware.sh, browse — while NOTHING persists (all RAM). A whole config session evaporated on reboot, and "rebooted into macOS, no Ubuntu partition" was the first visible symptom. Detect before configuring anything: `whoami` returns `ubuntu` on the live session (installed system has the user's chosen name), and `diskutil list`/`lsblk` shows no Linux partition. The installer must be RUN explicitly — desktop icon may not render; launch via Activities search "install" or `sudo ubiquity` (22.04) / `sudo ubuntu-desktop-bootstrap` (24.04).
- **Verify "Install alongside macOS" actually preserved macOS** post-install (`lsblk`: APFS container still present?). This session the installer erased the whole disk — macOS gone, no dual-boot rollback, and firmware.sh Method 1 dead with it (its EFI stash was wiped). Method 3 covers that case.
- **Target Disk Mode is wrong** — it exposes the SSD to another computer; it doesn't boot installers.
- Boot picker isn't a "mode" — it's an interrupted normal startup.
- T2 Macs are slow to light the display pre-boot; allow ~10s of black screen.
- Current wpa_supplicant 2.11 regression breaks Broadcom Wi-Fi on Arch-family only; fix = iwd backend or `brcmfmac.feature_disable=0x82000`. Never install `broadcom-wl` — stock `brcmfmac` is the only correct driver.

## Post-install shell pitfalls

- **"could not resolve wiki.t2linux.org" / apt update DNS failures** on a fresh
  install — the site is fine; triage in order: (1) `ping -c1 1.1.1.1` — no reply
  means no connectivity at all (expected pre-firmware on Wi-Fi-only; plug in
  Ethernet). (2) Ping works but names don't → broken resolver:
  `echo "nameserver 1.1.1.1" | sudo tee /etc/resolv.conf` (fresh t2linux can come
  up with systemd-resolved pointing nowhere). (3) Bypass DNS entirely:
  `curl --resolve wiki.t2linux.org:443:104.21.79.20 -sLo firmware.sh https://wiki.t2linux.org/tools/firmware.sh`
  (verify the IP first from a working box — it's Cloudflare-fronted and may rotate).
- Fresh t2linux Ubuntu installs may come up with a broken PATH (`sudo`, `curl`, `snap` all "not found"). Fix immediately: `export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin`. Persists only for the session — a clobbered `~/.profile` is the usual root cause; check for a stray `export PATH=...` that overwrites instead of appends.
- Default login user is `ubuntu` (not root) — needs `sudo` prefix.
- `telegram-desktop` is in the **universe** repo; `sudo snap install telegram-desktop` is the fastest path on a fresh install.

## Hermes migration pitfalls (proven 2026-06-12)

When migrating Hermes from another host via rsync, the venv packages do NOT transfer — rsync copies `~/.hermes/` data but not `/usr/local/lib/hermes-agent/venv/`. Any packages installed into that venv on the old host must be reinstalled manually. The knowledge DB stack is the most common gap:

```bash
uv pip install --python /usr/local/lib/hermes-agent/venv/bin/python3 \
  lancedb==0.33.0 pylance==7.0.0 pandas==3.0.3 pyarrow==24.0.0 \
  numpy==2.4.3 "sentence-transformers==5.5.1"
```

Verify: `python3 ~/.hermes/scripts/knowledge.py status` → should show fact count, not ImportError.

These packages are also wiped by `hermes update` (venv rebuild). `patch_guard.py` has a `_heal_knowledge_db_packages()` guard that auto-reinstalls them — verify it's present and silent after any update.

The SSH key rotates when the gateway restarts on a new host. After migration, add the new key to all remote hosts (ash-1, hil-1, etc.): `cat ~/.ssh/id_ed25519.pub` → append to each host's `/root/.ssh/authorized_keys`.

## Why this matters for Hermes

2018 mini + Ubuntu = same-OS migration target for Hermes (rsync ~/.hermes + venv + systemd units + Tailscale join; only real work is re-pointing hardcoded IPs). Intel macOS is EOL-track (~2028 security cutoff) — Linux is the right long-term OS for this hardware. macOS-target migration would instead cost launchd rewrites + /root→/Users path surgery.
