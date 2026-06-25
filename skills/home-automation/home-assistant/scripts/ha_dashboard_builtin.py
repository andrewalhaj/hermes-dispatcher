#!/usr/bin/env python3
"""
Build a Home Assistant storage-mode Lovelace dashboard using ONLY built-in cards
(tile + light-brightness feature, thermostat, heading). Zero custom-JS dependency,
so it cannot render silently-empty the way Mushroom/Bubble Card do.

Usage:
  1. Edit the LIGHTS / SWITCHES / CLIMATE lists below for the target setup.
  2. scp this into the HA container's /tmp (or `docker cp`).
  3. docker exec homeassistant python3 /tmp/ha_dashboard_builtin.py
  4. docker restart homeassistant
  5. Reload the dashboard in a plain browser.

It backs up the existing storage file to <file>.bak.<epoch> before writing.
"""
import json, time, os

# url_path of the custom dashboard (NOT 'home'/'lovelace' — those are reserved for Overview)
URL_PATH = "andrew-home"
STORE = f"/config/.storage/lovelace.{URL_PATH}"
THEME = "andrew_dark"          # set to None to inherit the global theme

# (entity_id, display_name) — each gets a tile with a drag-to-dim brightness slider
LIGHTS = [
    ("light.living_room_lamp", "Living Room Lamp"),
    ("light.lantern_lamp", "Lantern Lamp"),
    ("light.tv_bias_light", "TV Bias Light"),
    ("light.office_light", "Office Light"),
    ("light.bathroom_1", "Bathroom 1"),
    ("light.bathroom_2", "Bathroom 2"),
    ("light.bathroom_3", "Bathroom 3"),
]
# (entity_id, display_name, mdi_icon) — plain on/off tiles
SWITCHES = [
    ("switch.office_fan", "Office Fan", "mdi:fan"),
    ("switch.bathroom_group", "Bathroom Group", "mdi:lightbulb-group"),
    ("switch.office_group", "Office Group", "mdi:lightbulb-group"),
    ("switch.lantern_floor_lamp", "Lantern Floor Lamp", "mdi:floor-lamp"),
]
CLIMATE_ENTITY = "climate.sensi_thermostat"
CLIMATE_SENSORS = [
    ("sensor.sensi_thermostat_temperature", "Temperature"),
    ("sensor.sensi_thermostat_humidity", "Humidity"),
    ("binary_sensor.sensi_thermostat_online", "Online"),
]


def light_tile(eid, name):
    return {"type": "tile", "entity": eid, "name": name,
            "features_position": "bottom",
            "features": [{"type": "light-brightness"}]}

def switch_tile(eid, name, icon):
    return {"type": "tile", "entity": eid, "name": name, "icon": icon}

def heading(txt, icon=None):
    h = {"type": "heading", "heading": txt, "heading_style": "title"}
    if icon:
        h["icon"] = icon
    return h

def view(title, path, sections, max_columns=3):
    v = {"title": title, "path": path, "type": "sections",
         "max_columns": max_columns, "sections": sections}
    if THEME:
        v["theme"] = THEME
    return v

def grid(cards):
    return {"type": "grid", "cards": cards}


home = view("Home", "home", [
    grid([heading("Lights", "mdi:lightbulb-group")] + [light_tile(e, n) for e, n in LIGHTS]),
    grid([heading("Switches & Fan", "mdi:toggle-switch")] + [switch_tile(e, n, i) for e, n, i in SWITCHES]),
    grid([heading("Climate", "mdi:thermostat"),
          {"type": "thermostat", "entity": CLIMATE_ENTITY}] +
         [{"type": "tile", "entity": e, "name": n} for e, n in CLIMATE_SENSORS[:2]]),
])

climate = view("Climate", "climate", [
    grid([heading("Thermostat", "mdi:thermostat"),
          {"type": "thermostat", "entity": CLIMATE_ENTITY}]),
    grid([heading("Readings", "mdi:gauge")] +
         [{"type": "tile", "entity": e, "name": n} for e, n in CLIMATE_SENSORS]),
], max_columns=2)

lightsview = view("Lights", "lights", [
    grid([heading("All Lights", "mdi:lightbulb-multiple")] + [light_tile(e, n) for e, n in LIGHTS]),
    grid([heading("Groups & Fan", "mdi:toggle-switch")] + [switch_tile(e, n, i) for e, n, i in SWITCHES]),
])

config = {"title": "Home", "views": [home, climate, lightsview]}

# --- write with backup ---
store = json.load(open(STORE))
bak = f"{STORE}.bak.{int(time.time())}"
with open(bak, "w") as f:
    json.dump(store, f, indent=2)
store["data"]["config"] = config
with open(STORE, "w") as f:
    json.dump(store, f, indent=2)

# audit: confirm zero custom cards
types = {c.get("type") for v in config["views"] for s in v["sections"] for c in s["cards"]}
custom = [t for t in types if str(t).startswith("custom:")]
print("WROTE", STORE, "| backup:", bak)
print("views:", [v["title"] for v in config["views"]])
print("card types:", sorted(types))
print("custom cards:", custom or "NONE (good)")
