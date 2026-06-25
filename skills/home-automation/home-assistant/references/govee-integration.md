# Govee → Home Assistant Integration

Connecting Govee smart devices to HA. Two approaches; the **command_line** approach is the reliable one.

## Approach Comparison

| Approach | Devices seen | Control | State | Verdict |
|----------|-------------|---------|-------|---------|
| LaggAt `hacs-govee` integration | 3 of 9 (only some SKUs) | on/off + brightness/color | Crashes on learning-storage bug → `unavailable` | **Avoid** |
| `command_line` switches + `govee.py` | All 9 | on/off (script supports color/brightness/temp too) | Reliable via OpenAPI v1 state endpoint | **Use this** |

**Why LaggAt fails:** It uses a different/older Govee API that only enumerates a subset of devices, and its `learning_storage.py` makes blocking file writes inside the event loop that fail on HA 2026.6 + Python 3.14. State polling crashes → entities show `unavailable`.

**Why command_line wins:** Reuses the already-working `~/.hermes/scripts/govee.py` (OpenAPI v1 at `openapi.api.govee.com/router/api/v1`) which sees all 9 devices. HA just shells out to it.

## Setup

### 1. Copy govee.py into the HA container + provide API key

```bash
scp ~/.hermes/scripts/govee.py root@VPS:/tmp/govee.py
ssh root@VPS "docker cp /tmp/govee.py homeassistant:/usr/local/bin/govee.py"
# Script reads GOVEE_API_KEY from ~/.hermes/.env — provide it inside the container:
grep GOVEE_API_KEY ~/.hermes/.env > /tmp/govee_env.txt
scp /tmp/govee_env.txt root@VPS:/tmp/
ssh root@VPS "docker exec homeassistant mkdir -p /root/.hermes && docker cp /tmp/govee_env.txt homeassistant:/root/.hermes/.env"
```

### 2. govee.py needs a `status` command

The `status <name>` subcommand queries the OpenAPI v1 device-state endpoint (`/device/state`, NOT `/device/devices/state` which 404s) and returns `on`/`off`/`unavailable`. It reads BOTH the `online` capability (returns `unavailable` if offline) and `powerSwitch`. Required for HA's `command_state`.

### 3. command_line config (HA 2026.x schema)

**Critical:** Modern HA requires `command_line:` as a TOP-LEVEL key, NOT `switch: platform: command_line` (that's the deprecated pre-2022 schema and fails with "Configuring the command_line integration under the switch platform key is not supported").

Each list item is ONE entity with a `name` key (NOT a dict of named switches):

```yaml
# /config/govee_switches.yaml
- switch:
    name: TV Bias Light
    command_on: 'python3 /usr/local/bin/govee.py on "TV"'
    command_off: 'python3 /usr/local/bin/govee.py off "TV"'
    command_state: 'python3 /usr/local/bin/govee.py status "TV"'
    value_template: '{{ value == "on" }}'
    command_timeout: 20
    scan_interval: 60
```

In `configuration.yaml`:
```yaml
command_line: !include govee_switches.yaml
```

### 4. Apostrophes in device names

For names like `Andrew's Office Fan`, use double-quoted YAML with escaped inner doubles around the device name — single-quoted YAML with `'\''` escaping breaks the parser:
```yaml
command_on: "python3 /usr/local/bin/govee.py on \"Andrew's Office Fan\""
```

## Pitfalls

- **`command_timeout` + `scan_interval` are mandatory when any device may go offline.** An offline Govee device makes the OpenAPI control call hang ~30s. Without `command_timeout: 20`, this blocks HA's executor and starves other switches' state polls (log: "Updating Command Line Switch X took longer than the scheduled update interval"). `scan_interval: 60` reduces poll frequency.
- **Offline ≠ broken.** A device returning `{"code":400,"msg":"Device is offline"}` is just off Wi-Fi. The plumbing is fine — verify with an ONLINE device before debugging config.
- **command_line switches don't appear in `core.entity_registry`.** They live in the state machine only. Verify via `/api/states` (need a valid token), not the registry file.
- **Manually-injected long-lived tokens get pruned on restart.** HA prunes long-lived access tokens lacking a credential link. To get a token that survives, use the admin login flow (`/auth/login_flow` → submit creds → exchange `result` at `/auth/token`) — see main SKILL.md Section 2.
- **HA state display lags device reality by up to `scan_interval`.** After a `turn_on`, the entity state may still read `off` until the next poll. Verify actual device state via `govee.py status <name>` directly, not the HA entity state, when testing.
- **LaggAt leftovers:** If LaggAt was tried first, remove its config entry from `core.config_entries` (domain `govee`) and `rm /config/custom_components/govee` to stop the `unavailable` light entities and the learning-storage error spam.

## Verifying End-to-End

The authoritative test: call HA's service, then check the DEVICE directly (not the HA entity):
```bash
# Via HA (using a valid token from login flow):
POST /api/services/switch/turn_on {"entity_id": "switch.tv_bias_light"}
# Then verify at device level:
docker exec homeassistant python3 /usr/local/bin/govee.py status TV   # -> "on"
```
If the device flips, the chain works — even if the HA entity state hasn't refreshed yet.

## Device Inventory (9 devices — ALL on command_line)

LaggAt was DROPPED entirely (2026-06-04). All 9 devices are now command_line switches: Living Room Lamp, Lantern Floor Lamp, TV (bias light), Office Fan, Bathroom Group, Office Group, Bathroom Light 1/2/3. All on/off. The govee.py script also supports `color R G B`, `brightness PCT`, `temp KELVIN` for richer control if light-template entities are built later.

## Removing LaggAt Cleanly (the migration that worked)

When LaggAt's 3 bathroom lights kept showing `unavailable` (integration bug, NOT Wi-Fi — verified the devices were online via `govee.py status`), the fix was to drop LaggAt and put those 3 on command_line too:

1. Remove the `govee` domain config entry from `.storage/core.config_entries`
2. Remove all `platform == "govee"` entities from `.storage/core.entity_registry`
3. `rm -rf /config/custom_components/govee` and `rm -f /config/govee_learning.yaml`
4. Add the 3 bathroom lights to `govee_switches.yaml` as command_line switches
5. Restart, verify 0 `custom_components.govee` errors and 9 switches present

Entity IDs chosen: `switch.bathroom_light_1/2/3` (avoid colliding with the existing `switch.bathroom_group`). Verified end-to-end: HA `turn_off` on `switch.bathroom_light_1` flipped the physical device.
