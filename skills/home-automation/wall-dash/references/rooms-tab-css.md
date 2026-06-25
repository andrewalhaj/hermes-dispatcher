# Rooms Tab CSS — extracted from live `dashboard.css`

Source: `/root/wall-dash/dashboard.css` (host 178.156.246.115), captured 2026-06-07.
CSS is in a SEPARATE file, not inline in `index.html`. Layout is **Model A** (block/row, no subtabs) — see SKILL.md "Rooms view — TWO layout models".

⚠️ This is a snapshot. The file gets refactored — re-read the live file before trusting line numbers or exact rules.

## Room tile component (lines ~184–232)

```css
/* ---------- Room group + tiles ---------- */
.room-tiles { display: flex; gap: 1.3rem; flex-wrap: wrap; }
.room-tiles > * { flex: 1 1 200px; min-width: 0; }
.three { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 2rem; }

.room-tile {
  padding: 1.3rem 1.2rem 1.1rem;
  display: flex; flex-direction: column; align-items: stretch; gap: 0.7rem;
  min-height: 13rem;
}
.rt-icon {
  width: 3.6rem; height: 3.6rem; border-radius: 50%; align-self: center;
  display: flex; align-items: center; justify-content: center; cursor: pointer;
  border: 2px solid rgba(255,255,255,0.30);
  background: rgba(0,0,0,0.12);
  transition: border-color 160ms ease, box-shadow 160ms ease, opacity 160ms ease;
}
.rt-icon .ic { width: 1.7rem; height: 1.7rem; }
.rt-icon.on { border-color: rgba(90,225,140,0.95); box-shadow: 0 0 16px rgba(80,220,130,0.5), inset 0 0 12px rgba(80,220,130,0.15); }
.rt-icon:not(.on) { opacity: 0.65; }
.rt-name { text-align: center; font-size: 1.18rem; font-weight: 600; text-shadow: 0 1px 4px rgba(0,0,0,0.3); }
.rt-state { text-align: center; font-size: 0.72rem; opacity: 0.55; letter-spacing: 0.12em; text-transform: uppercase; margin-top: -0.5rem; }
.rt-actions { display: flex; gap: 0.7rem; margin-top: auto; }
.rt-btn {
  flex: 1; display: flex; flex-direction: column; align-items: center; gap: 0.3rem;
  padding: 0.6rem 0.4rem; border-radius: 0.7rem; cursor: pointer; color: #fff; font: inherit;
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.10);
  transition: transform 140ms ease, background 140ms ease, box-shadow 140ms ease;
}
.rt-btn:hover { transform: translateY(-1px); background: rgba(255,255,255,0.13); }
.rt-btn .bi { width: 1.2rem; height: 1.2rem; opacity: 0.92; }
.rt-btn span { font-size: 0.82rem; letter-spacing: 0.01em; opacity: 0.92; }
.rt-btn.active { background: linear-gradient(180deg, rgba(255,205,110,0.4), rgba(240,165,70,0.22)); border-color: rgba(255,210,130,0.5); box-shadow: 0 0 12px rgba(255,190,90,0.3); }
.rt-slider { display: flex; align-items: center; gap: 0.6rem; }
.rt-slider .si { width: 1.2rem; height: 1.2rem; opacity: 0.85; flex-shrink: 0; }
.rt-slider input[type='range'] {
  flex: 1; -webkit-appearance: none; appearance: none; height: 0.42rem;
  border-radius: 999px; background: rgba(255,255,255,0.2); outline: none;
}
.rt-slider input[type='range']::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none; width: 1.05rem; height: 1.05rem; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,0.4); cursor: pointer; border: none;
}
.rt-slider input[type='range']::-moz-range-thumb {
  width: 1.05rem; height: 1.05rem; border-radius: 50%; background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.4); cursor: pointer; border: none;
}
.rt-val { font-size: 0.85rem; opacity: 0.7; min-width: 2.8rem; text-align: right; }
```

## View switching + Rooms-tab layout (lines ~234–250)

```css
/* ---------- View switching ---------- */
.view[hidden] { display: none !important; }

/* ---------- Rooms tab ---------- */
.room-block + .room-block { margin-top: 1.9rem; }
.room-block-head { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; margin: 0 0.1rem 0.9rem; }
.room-block-head .sec-title { margin: 0; }
.room-summary { font-size: 0.95rem; opacity: 0.5; letter-spacing: 0.04em; text-transform: uppercase; white-space: nowrap; }
.rooms-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 1.4rem; }
.rooms-grid .room-tile { min-height: 12rem; }

/* Living room: two wide tiles */
.rooms-grid.two { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }

/* Bottom row: three single-tile rooms side by side */
.room-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 2rem; margin-top: 1.9rem; }
.room-col .sec-title { margin: 0 0.1rem 0.9rem; }
```

## Layout map (Model A)

- `.room-block` + `.rooms-grid.two` → Living Room section, two wide tiles (`minmax(260px, 1fr)`).
- `.room-row` + `.room-col` → bottom row: Master Bedroom / Office / Bathroom, three tiles side by side (`minmax(240px, 1fr)`).
- `.room-tile` → tile shell (flex column, 13rem min-height); `.rt-icon` circular toggle (green glow when `.on`), `.rt-actions`/`.rt-btn` scene buttons (amber gradient when `.active`), `.rt-slider` brightness.
- Responsive `@media` grid redefinitions live further down (~line 391) — read live if touching breakpoints.
