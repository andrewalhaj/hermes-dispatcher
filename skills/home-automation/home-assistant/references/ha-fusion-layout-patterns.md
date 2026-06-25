# ha-fusion Layout Patterns (Andrew's conventions)

## Consolidation rule: lights + scenes go in one custom_panel

Andrew prefers related controls grouped into `custom_panel`s, not scattered as standalone buttons. A light and its scene picker belong in the same tile.

### Pattern 1 — Light + Scene Picker

```yaml
- type: custom_panel
  name: Living Room Lamp
  icon: mdi:lamp
  rows:
    - type: slider
      entity_id: light.living_room_lamp
    - type: buttons
      columns: 1
      items:
        - entity_id: input_select.govee_scene_lrl
```

- Slider row first (brightness control)
- Buttons row second (scene picker opens the input_select modal when tapped)
- Scene picker dropdown appears on tap — works because `input_select` entities in `buttons` rows open the select modal

### Pattern 2 — Multiple devices in one panel

```yaml
- type: custom_panel
  name: Nvidia Shield
  icon: mdi:television-play
  rows:
    - type: slider
      entity_id: light.tv_bias_light
    - type: buttons
      columns: 2
      items:
        - entity_id: media_player.unnamed_device
        - entity_id: input_select.govee_scene_tvbias
```

- Multiple entity types in the buttons row are supported (media_player + input_select)
- Each renders as its own button in the row
- `columns: 2` for two side-by-side; `columns: 1` for stacked

## Climate dial CSS tuning

The climate dial renders in `custom_panel` with `display: dial`. The CSS lives in `custom_style.css` on the HA host at `/root/ha-fusion/data/custom_style.css`. **Hot-reloads — no container restart needed.** Source patches only when adding new display modes or component behavior.

### Key CSS classes (scaled ~30% from original on 2026-06-04)

| Class | Controls | Current size |
|---|---|---|
| `.dial-tile` | Min height, padding | `min-height: 22rem`, `padding: 1.8rem` |
| `.dial-ring` | Ring dimensions, border | `width: 16rem`, `height: 16rem`, `border-width: 6px` |
| `.dial-target` | Target temp | `font-size: 5rem` |
| `.dial-target .deg` | Degree mark | `font-size: 2.8rem` |
| `.dial-room` | Room name below ring | `font-size: 1.5rem` |
| `.dial-status` | HVAC action + time | `font-size: 1.2rem` |
| `.dial-meta` | Current/humidity/fan rows | `font-size: 1.1rem` |

### Tuning workflow
1. SSH into 178.156.246.115
2. Back up: `cp /root/ha-fusion/data/custom_style.css /root/ha-fusion/data/custom_style.css.prev`
3. Edit the `.dial-*` class values
4. User reopens dashboard — CSS hot-reloads
5. If dial "looks wonky," bump ring and font sizes ~30% as a starting point

## Anti-patterns (do NOT do)
- Standalone scene picker buttons in section items — consolidate into custom_panel
- Inventing fields on custom_panel (`primary_row_id` does not exist)
- Placing a custom_panel AS a view (blanks the entire dashboard)
- Docker rebuild for CSS-only changes — `custom_style.css` hot-reloads
