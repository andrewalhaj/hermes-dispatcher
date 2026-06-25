---
name: shield-control
description: "Control Nvidia Shield TV via ADB over Tailscale."
category: home-automation
---

# Shield Control via ADB

Control the Nvidia Shield Android TV (model: mdarcy, Tailscale IP: 100.69.145.58, local IP: 10.0.0.45) via ADB from the backup VPS (178.156.246.115).

## Pre-requisites
- Tailscale must be active on both VPS and Shield (subnet routing enabled on Shield)
- ADB debugging enabled on Shield (Developer Options → Network debugging ON)
- ADB key authorized (one-time RSA prompt on TV screen)
- ADB server runs on backup VPS

## Connection
```bash
ssh root@178.156.246.115 "adb connect 100.69.145.58:5555"
```

## Key Commands

### Power
- Power toggle: `adb shell input keyevent KEYCODE_POWER`
- Sleep: `adb shell input keyevent KEYCODE_SLEEP`
- Wake: `adb shell input keyevent KEYCODE_WAKEUP`

### Volume
- Up: `adb shell input keyevent KEYCODE_VOLUME_UP`
- Down: `adb shell input keyevent KEYCODE_VOLUME_DOWN`
- Mute: `adb shell input keyevent KEYCODE_VOLUME_MUTE`

### Navigation
- Up/Down/Left/Right: `adb shell input keyevent KEYCODE_DPAD_UP` (etc.)
- Select/Enter: `adb shell input keyevent KEYCODE_DPAD_CENTER`
- Home: `adb shell input keyevent KEYCODE_HOME`
- Back: `adb shell input keyevent KEYCODE_BACK`
- Recent apps: `adb shell input keyevent KEYCODE_APP_SWITCH`

### Media Control
- Play/Pause: `adb shell input keyevent KEYCODE_MEDIA_PLAY_PAUSE`
- Stop: `adb shell input keyevent KEYCODE_MEDIA_STOP`
- Next: `adb shell input keyevent KEYCODE_MEDIA_NEXT`
- Previous: `adb shell input keyevent KEYCODE_MEDIA_PREVIOUS`
- Rewind: `adb shell input keyevent KEYCODE_MEDIA_REWIND`
- Fast Forward: `adb shell input keyevent KEYCODE_MEDIA_FAST_FORWARD`

### Pulling up a title without auto-playing (Plex)
When asked to "pull up" a show/movie but NOT start playback, navigate to the detail page and stop:
1. Launch Plex (monkey command above), wait ~8s.
2. `adb shell input keyevent KEYCODE_SEARCH` -> opens search.
3. `adb shell input text 'One%sPiece'` (use `%s` for spaces in `input text`).
4. Wait ~4s for results, screenshot to verify, then DPAD to the correct result tile and `KEYCODE_DPAD_CENTER`.
5. This lands on the show/movie DETAIL page (seasons/episodes listed) — it does NOT auto-play. Confirm via screenshot before reporting done.
Note: Plex may show multiple sources for a title (e.g. a "Max Nas" / external library tile). Clicking into a source tile opens that library's full show page with all seasons/arcs. Clicking a tile = navigate, not play; playback only starts on an explicit episode/Play-button select.

### Playing a SPECIFIC season/episode on Prime Video (the hard case)
Prime Video's Android TV app (`com.amazon.ignition`) is the trap-heavy one. Asking for "S1 E1" of a show the user is mid-watching in a LATER season is NOT a simple launch — three UI behaviors fight blind ADB navigation:

1. **The Play button defaults to RESUME the user's current season/episode**, not S1E1. If they're on S4, the big button says "Resume S4 E1". You MUST open the season selector and switch to Season 1 before playing.
2. **Center-press on the title keeps resolving to Resume/Play, not "open season dropdown".** Reaching the season dropdown via vertical DPAD is fiddly — the focus often lands on the episode thumbnail row (just below the dropdown) and a center-press there starts S4 playback. Land on the dropdown, screenshot-CONFIRM the dropdown itself is focused (darker/outlined, NOT an episode tile), THEN center-press.
3. **The home-screen hero carousel AUTO-ROTATES every few seconds.** A DPAD_RIGHT/LEFT issued from the hero banner can drift onto a *different* title than the one in your last screenshot (saw it jump Vox Machina → Kill Blue → period-drama promo). Do not navigate blind off the hero. Use the left **sidebar search** for a deterministic path to a title instead of the carousel.

Reliable sequence for "play <show> S<x> E<y>":
1. Launch Prime: `adb shell am start -n com.amazon.amazonvideo.livingroom/com.amazon.ignition.IgnitionActivity` (see package note below).
2. DPAD_LEFT into the left sidebar rail, DPAD_UP to the **search** (magnifying-glass) icon, screenshot-confirm it's focused, center-press.
3. Type the title (`adb shell input text 'Vox%sMachina'`), open the detail page.
4. Move to the **season selector dropdown** (shows "Season N"). Screenshot-confirm the DROPDOWN is the focused element before center-press — not the Play button, not an episode tile.
5. Open it, DPAD to Season 1, center-press.
6. DPAD to Episode 1 tile, center-press to play. Screenshot-verify the right S/E is loading (subtitles/title card) before reporting done.

**If blind navigation keeps mis-resolving (started the wrong episode 2×), STOP and hand the last 3 clicks to the user** — be honest about the Resume-default + dropdown trap rather than risking starting the wrong episode again. Leaving them on the detail page 3 clicks from done is a legitimate outcome.

**Prime Video package + activity (discovered live):**
- Real package: `com.amazon.amazonvideo.livingroom` (enabled=1), launcher activity `com.amazon.ignition.IgnitionActivity`. Launch with `am start -n com.amazon.amazonvideo.livingroom/com.amazon.ignition.IgnitionActivity`.
- The `...livingroom.nvidia` variant is a DUMMY (`enabled=0`, "No activities found to run" on monkey) — do NOT use it.
- `monkey -p com.amazon.amazonvideo.livingroom` AND `cmd package resolve-activity --brief` BOTH return "No activity found" for this package even though it launches fine via explicit `am start`. To find the launcher when monkey/resolve fail: `dumpsys package <pkg> | grep -iE "Activity|enabled="` and look for the `IgnitionActivity` resolver entry + `enabled=1`.

Full session transcript (carousel drift, dropdown-vs-Resume mis-resolves, package discovery): `references/prime-video-navigation.md`.

## Verifying state visually
Capture and pull a screenshot to confirm what's on screen (snapshot/dumpsys alone won't show app UI content):
```bash
adb -s 100.69.145.58:5555 exec-out screencap -p > /tmp/shield.png
scp root@178.156.246.115:/tmp/shield.png /tmp/shield.png
```
Then inspect /tmp/shield.png. Always screenshot-verify before claiming a title is "pulled up" or "playing".

## Launch Apps
```bash
# Netflix
adb shell am start -n com.netflix.ninja/.MainActivity

# YouTube  
adb shell am start -n com.google.android.youtube.tv/.MainActivity

# Plex — DO NOT use a hardcoded activity name; it changes across app versions
# (e.g. .activity.SplashActivity is wrong on current builds -> "Activity class does not exist").
# Launch by package via monkey instead — resilient to activity renames:
adb shell monkey -p com.plexapp.android -c android.intent.category.LAUNCHER 1
# To discover the real launcher activity for any package if needed:
#   adb shell cmd package resolve-activity --brief <package> | tail -n 1

# Settings
adb shell am start -n com.android.tv.settings/.MainSettings
```

### Query State
- Current app: `adb shell dumpsys window | grep mCurrentFocus`
- Screen state: `adb shell dumpsys power | grep "Display Power"`
- Device info: `adb shell getprop ro.product.model`

## All commands run from backup VPS via SSH
Prefix all adb commands with: `ssh root@178.156.246.115 "adb -s 100.69.145.58:5555 ..."`

## Home Assistant (working)
HA is running on backup VPS (178.156.246.115:8123), Docker container `homeassistant`, `--network host`.

**Entity**: `media_player.unnamed_device` — this is the hardcoded entity_id from HA's androidtv integration in 2026.6. It CANNOT be renamed via API (not in entity registry, customize.yaml ignored). Rename it via the HA web UI: tap entity → ⚙️ → Rename to "TV" (5 seconds).

**Integration config** (in `/root/homeassistant/config/.storage/core.config_entries`):
- host: `100.69.145.58` (Tailscale IP — Docker can't reach 10.0.0.45)
- port: 5555
- adbkey: `/config/.storage/adbkey`
- device_class: `androidtv`

**Auth**: User `hermes_admin` / password `@May161998`. Use login flow to get tokens:
```python
import requests
BASE = "http://localhost:8123"
# Step 1: get flow
r = requests.post(f"{BASE}/auth/login_flow", json={
    "client_id": "http://localhost:8123/",
    "redirect_uri": "http://localhost:8123/",
    "handler": ["homeassistant", None]
})
flow_id = r.json()["flow_id"]
# Step 2: submit credentials
r = requests.post(f"{BASE}/auth/login_flow/{flow_id}", json={
    "client_id": "http://localhost:8123/",
    "username": "hermes_admin",
    "password": "hermes_ha_2026"
})
code = r.json()["result"]
# Step 3: get access token
r = requests.post(f"{BASE}/auth/token", data={
    "grant_type": "authorization_code",
    "code": code,
    "client_id": "http://localhost:8123/"
})
access_token = r.json()["access_token"]
```

**API examples**:
```bash
# Volume down
curl -X POST http://localhost:8123/api/services/media_player/volume_down \
  -H "Authorization: Bearer *** application/json" \
  -d '{"entity_id": "media_player.unnamed_device"}'

# Pause
curl -X POST http://localhost:8123/api/services/media_player/media_pause \
  -H "Authorization: Bearer *** application/json" \
  -d '{"entity_id": "media_player.unnamed_device"}'

# Select source (launch app)
curl -X POST http://localhost:8123/api/services/media_player/select_source \
  -H "Authorization: Bearer *** application/json" \
  -d '{"entity_id": "media_player.unnamed_device", "source": "Netflix"}'

# Get state
curl -s http://localhost:8123/api/states/media_player.unnamed_device \
  -H "Authorization: Bearer ***
```

**Important**: Docker container CAN reach 100.69.145.58 but NOT 10.0.0.45 (Tailscale subnet routes don't propagate into containers). Always use Tailscale IP in HA config.

## Pitfalls
- **`KEYCODE_SEARCH` opens the Shield's SYSTEM Google Assistant (voice), NOT the in-app search.** For in-app search use the app's own search affordance (Prime: left-sidebar magnifying-glass icon → DPAD navigate → center-press). The old Plex note above using `KEYCODE_SEARCH` worked for Plex but is NOT a universal pattern — verify with a screenshot that an in-app search field (not the Assistant chip UI) opened.
- **Prime Video defaults the Play button to RESUME the user's current season** — playing "S1 E1" requires opening the season dropdown first. See the Prime section above. Don't assume Play = start from the beginning.
## Navigating streaming-app UIs blind (Prime Video, Plex, etc.)

ADB has NO accessibility tree for these apps — `dumpsys window | grep mCurrentFocus` only gives you the foreground Activity, NOT which on-screen element is focused. So every DPAD move must be screenshot-verified before the next keypress, or you navigate blind and drift. Workflow that works: keypress → `sleep 1` → screencap → vision-check focus → next keypress. Slow but deterministic.

### The "Resume" trap — playing a SPECIFIC episode on a resume-state title
When a show has watch progress, the detail-page Play button defaults to the RESUME point (e.g. "Resume S4 E1"), not S1E1. A naive center-press on the title plays the resume episode. To reach a different season/episode you MUST open the **season selector dropdown** first and switch seasons before pressing Play. Pitfall observed on Prime's Ignition UI: center-presses kept resolving to Resume even when I thought the dropdown was focused — focus was actually one row off. The dropdown sits on its OWN row, separate from the Play button and separate from the episode thumbnail row. Verify the dropdown itself has the focus highlight (darker/brighter background) via screenshot BEFORE pressing center, or you'll start the resume episode by accident. If you do mis-fire into playback, `KEYCODE_BACK` once exits the player back to the detail page (a SECOND back may pop an "Exit the application" OK/Cancel dialog — DPAD_DOWN to Cancel, do not OK out of the app).

### Auto-rotating hero carousels poison blind navigation
The Android-TV HOME screen of Prime Video (and similar apps) has an auto-rotating featured/hero carousel. The focused title CHANGES on its own between your screenshot and your keypress, so a DPAD_RIGHT you intended to move Play→More-details instead lands on a different show entirely. Do NOT navigate the hero banner blind. Prefer a DETERMINISTIC entry point instead: the left-sidebar **Search** icon, or **Continue Watching** tiles (which are static, not rotating). For "just play X" where X is already in progress, the Continue Watching tile is the fastest reliable path — but note it may open the DETAIL/preplay page (one more center-press on the Play button needed) rather than auto-playing.

### Confirming playback actually started (don't trust the screenshot)
A clean fullscreen video frame with no UI overlay looks identical to a paused/loading frame to a vision model — it'll often say "no playback controls, probably not playing." Get GROUND TRUTH from the media session instead:
```bash
adb -s <ip>:5555 shell dumpsys media_session | grep -iE 'package|state=PlaybackState'
```
`state=3` = PLAYING, `state=2` = PAUSED. A `position=` that advances between two calls confirms live playback. This is authoritative where pixels are ambiguous.

### Launching an app whose monkey/package name fails
`monkey -p <pkg>` returns "No activities found to run" when the package has no LEANBACK launcher activity OR the variant is a stub. Prime Video on Shield ships TWO packages: `com.amazon.amazonvideo.livingroom` (real, `enabled=1`, launcher `com.amazon.ignition.IgnitionActivity`) and `com.amazon.amazonvideo.livingroom.nvidia` (stub, `enabled=0`, no launchable activity — monkey aborts). When monkey fails, find the real launcher with:
```bash
adb -s <ip>:5555 shell 'dumpsys package <pkg> | grep -iE "Activity Resolver|enabled=|com.amazon.*Activity"'
```
then launch the resolved activity directly: `adb shell am start -n com.amazon.amazonvideo.livingroom/com.amazon.ignition.IgnitionActivity`. (As the Plex note already says: package names/activities change across app versions — resolve, don't hardcode.)

## Pitfalls
- ADB network debugging auto-disables after timeout on Android TV — user must re-enable in Developer Options
- Shield must appear as "active; direct" in `tailscale status` on VPS
- Subnet routing must be enabled on Shield for VPS to reach 10.0.0.45
- If ADB shows "failed to authenticate", check TV screen for RSA key prompt
- **`KEYCODE_SEARCH` opens the Shield SYSTEM Google Assistant, not the in-app search.** To search inside Prime/Plex, navigate to the app's own sidebar magnifying-glass icon and select it — don't rely on the global SEARCH keycode.
- **Vision models don't recognize Plex's TV layout as Plex** (they'll call the Home/Trending/Activity/Find Friends tabs "a social app"). Trust `mCurrentFocus=com.plexapp.android/...HomeActivityTV` over the vision model's app identification.
