---
name: govee-control
description: "Control Govee devices: lights, fans, plugs via API."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [govee, smart-home, lights, home-automation]
    created_by: agent
load_when:
  - "user asks to control Govee devices"
  - "user mentions lights, lamps, fan, TV bias lighting, bathroom lights"
  - "user gives a Govee API key or asks about Govee integration"
---

# Govee Device Control

Control Govee smart home devices via the OpenAPI. Script at `~/.hermes/scripts/govee.py`.

## Quick Commands

```
python3 ~/.hermes/scripts/govee.py list                          # List all devices
python3 ~/.hermes/scripts/govee.py on "Living Room Lamp"         # Turn on
python3 ~/.hermes/scripts/govee.py off "Living Room Lamp"        # Turn off
python3 ~/.hermes/scripts/govee.py color 255 100 0 "TV"          # Set orange
python3 ~/.hermes/scripts/govee.py brightness 50 "Bathroom 1"    # Set 50% brightness
python3 ~/.hermes/scripts/govee.py temp 4000 "Living Room Lamp"  # Set warm white
```

## Current Devices (9 total)

| Name | SKU | Key Capabilities |
|------|-----|-----------------|
| Living Room Lamp | H1401 | RGB, temp, brightness, scenes, music |
| Lantern Floor Lamp | H1630 | RGB, segments, temp, gradient, DreamView |
| TV | H6604 | RGB, segments, temp, gradient, DreamView, HDMI |
| Bathroom 1 | H6006 | RGB, temp, brightness, scenes |
| Bathroom 2 | H6006 | RGB, temp, brightness, scenes |
| Bathroom 3 | H6006 | RGB, temp, brightness, scenes |
| Andrew's Office Fan | H1310 | RGB, segments, temp, fan toggle/speed, airflow |
| Bathroom (group) | SameModeGroup | On/off only |
| Andrew's Office (group) | SameModeGroup | On/off only |

## How Hermes Controls Devices

Use `terminal()` to call the script:

```python
terminal(command='python3 ~/.hermes/scripts/govee.py on "Living Room Lamp"')
terminal(command='python3 ~/.hermes/scripts/govee.py off "Bathroom"')
terminal(command='python3 ~/.hermes/scripts/govee.py color 0 0 255 "TV"')  # blue
terminal(command='python3 ~/.hermes/scripts/govee.py brightness 30 "Bathroom 1"')
```

**Color values:** RGB integers 0-255 each. Examples:
- Red: `255 0 0`
- Blue: `0 0 255`  
- Warm white: `255 200 100` (or use `temp` command)
- Purple: `128 0 255`

**Temperature values:** Kelvin, typically 2000-9000. 2700=warm, 4000=neutral, 6500=cool.

**Brightness:** 1-100 percent.

## How It Works

Script reads `GOVEE_API_KEY` from `~/.hermes/.env`, calls the Govee OpenAPI at `openapi.api.govee.com`. Name matching is case-insensitive partial — "bathroom" matches "Bathroom 1", "living" matches "Living Room Lamp".

## Combined Automations

This skill is a sibling of `homeassistant`. With both connected, Hermes can orchestrate multi-device routines — e.g., "movie night" dims Govee lights AND turns on the Shield via HA. When the user asks for cross-device automation, load both skills.

## Adding More Devices

If you buy new Govee devices, re-run `python3 ~/.hermes/scripts/govee.py list` to see them. Update this skill's device table.

## Pitfalls

- **Name collisions with groups:** If you have both a device and a group with similar names (e.g., "Andrew's Office Fan" and "Andrew's Office" group), use the exact name to avoid ambiguity. The script now tries exact match before partial match, but identical-prefix names (like "Bathroom" vs "Bathroom 1") still collide. In those cases, call the API directly with the device ID — see `references/direct-api-control.md`.
- **Offline devices:** Devices return error 400 with "Device is offline" — they can't be controlled until reconnected to Wi-Fi. Partial successes are common (group turns off but individual device is offline).
- Group controls (SameModeGroup) only support on/off — no color or brightness
- TV and Lantern Floor Lamp support segmented control but the script currently uses whole-device commands
- API key is per Govee account, not per device
- Some capabilities (lightScene, musicMode) require knowing scene IDs. Scene control runs via `paramId`/`id` (official OpenAPI) wired through HA input_select → shell_command. The official API returns **no scene artwork** — for the colorful Govee-app scene thumbnails, use the auth-free undocumented app endpoint documented in `references/scene-artwork-api.md` (runnable fetcher at `scripts/fetch_scene_art.py`).
