# VeSync Integration — Direct Config Entry Injection

VeSync (Levoit air purifiers, Etekcity smart plugs, Cosori) is a native HA integration
(`homeassistant.components.vesync`) but does NOT support YAML configuration. Adding
`vesync:` to `configuration.yaml` produces:
```
ERROR: The vesync integration does not support YAML setup, please remove it from your configuration file
```

## Direct config-entry injection (when REST API auth is blocked)

When you can't get a working long-lived access token for the config flow API
(token 401s, admin login flow results are transient), write the config entry
directly to `.storage/core.config_entries`:

```json
{
  "domain": "vesync",
  "title": "VeSync",
  "data": {
    "username": "user@example.com",
    "password": "plaintext-password"
  },
  "source": "user",
  "version": 1,
  "minor_version": 1,
  "unique_id": "<numeric-account-id>",
  "entry_id": "<32-char hex uuid>",
  "options": {},
  "pref_disable_new_entities": false,
  "pref_disable_polling": false,
  "disabled_by": null,
  "discovery_keys": {},
  "created_at": "<ISO-8601>",
  "modified_at": "<ISO-8601>",
  "subentries": []
}
```

**Key fields:**
- `unique_id`: Set initially to a random string (`secrets.token_hex(8)`). HA will overwrite this with the numeric VeSync account ID on successful auth (e.g., `"16023137"`).
- `minor_version`: HA will increment this through the flow steps — starts at 1, ends at 3 after successful setup.
- `password`: Stored in plaintext inside the config entry data. Credentials are scoped to the VeSync API auth only.

## Post-injection

1. Restart HA (`docker restart homeassistant`)
2. HA processes the config entry on boot, authenticates to VeSync, discovers devices
3. **Check entity registry** — entities appear in `.storage/core.entity_registry` within seconds of boot
4. **Check device registry** — devices appear in `.storage/core.device_registry` with manufacturer/model/identifiers

## Entities created (Levoit Vital 200S, model LAP-V201S-WUS)

Per device, approximately 7 entities:

| Entity | Type | Notes |
|--------|------|-------|
| `fan.<device_name>` | fan | On/off, speed, presets (auto/pet/sleep), supported_features: 57 |
| `sensor.<device_name>_air_quality` | sensor | Air quality indicator |
| `sensor.<device_name>_pm2_5` | sensor | PM2.5 µg/m³, device_class: pm25 |
| `sensor.<device_name>_filter_lifetime` | sensor | Filter life %, entity_category: diagnostic |
| `switch.<device_name>_display` | switch | Display on/off |
| `switch.<device_name>_child_lock` | switch | Child lock |
| `update.<device_name>_firmware` | update | Firmware updates, entity_category: diagnostic |

Device name is derived from the VeSync app's device alias (e.g., "Living Room", "Dining Room").
The entity_id becomes `fan.living_room`, `fan.dining_room`, etc.

## Pitfalls

- **Password special characters in shell:** VeSync credentials are passed through SSH → docker → bash → Python. A `$` in the password (e.g., `$May161998`) gets interpreted by bash unless inside a quoted heredoc (`<< 'PYEOF'`). If scp'ing a script, the password is safe in the file body but may cause issues in inline `ssh ... python3 -c "..."` one-liners. Always write scripts to files first, scp, then execute remotely.

- **`unique_id` auto-overwrite:** HA replaces the initial random `unique_id` with the numeric VeSync account ID on first successful auth. Don't be alarmed when the value changes — it's expected behavior.

## Dashboard placement (Wall-dash)

Andrew's primary dashboard is the Wall-dash at port 5051 (nginx-served SPA, NOT Lovelace). Adding purifier tiles to the Wall-dash involves editing the static `index.html`: adding room tiles with `purifier-cell` class, WebSocket refresh functions, and subtab navigation entries. Full architecture: `references/wall-dash-architecture.md`.
