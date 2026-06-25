# Design System — Colors, Typography, Spacing, Components

## Color Palette (verified from live bundle)

### Base surfaces
```
Background (main):     #0a0e16   (near-black navy)
Background (mid):      #0d121d   (slightly lighter navy)
Sidebar:               #11151f   (dark navy, sidebar bg)
Card surface:          #12161f   (card backgrounds)
Card surface (hover):  #141a26   (slightly lighter card)
Elevated surface:      #161b27   (modals, dropdowns)
Border:                rgba(255,255,255,0.07)  (subtle borders)
Border strong:         rgba(255,255,255,0.12)
Separator:             rgba(255,255,255,0.06)
```

### Text
```
Text primary:     #e9ebf2   (near-white, main content)
Text secondary:   #cdd2e0   (slightly muted)
Text muted:       #8c92a6   (section labels, secondary info)
Text very muted:  #6a7088   (placeholders, timestamps)
Text dimmed:      #565d72   (disabled, placeholder text)
```

### Accent — Gold/Amber (primary brand color)
```
Accent primary:   #f6b73c   (gold — the defining color)
Accent glow:      rgba(246,183,60,0.15)
Accent dim:       rgba(246,183,60,0.08)
```

### Semantic colors
```
Teal (running/active):    #2dd4bf
Teal dim:                 rgba(45,212,191,0.12)
Blue (info/workers):      #5aa2f0
Blue light:               #8fb4ec
Green (success/live):     #4ade80
Red (blocked/error):      #fb6f6f
Red dim:                  rgba(251,111,111,0.12)
Purple (memory/emergent): #9b8cff
Purple dim:               rgba(155,140,255,0.12)
```

### Galaxy tier colors (for Memory Galaxy panel)
```
Notes:         #f6b73c  (gold)
User Profile:  #5aa2f0  (blue)
Agent Soul:    #9b8cff  (purple)
Agent Rules:   #f472b6  (pink)
Context:       #2dd4bf  (teal)
Knowledge:     #4ade80  (green)
Conversations: #fb6f6f  (coral)
```

### Kanban status colors
```
Triage:  #6a7088  (gray-muted)
Todo:    #5aa2f0  (blue)
Ready:   #f6b73c  (gold)
Running: #2dd4bf  (teal)
Blocked: #fb6f6f  (red)
Done:    #4ade80  (green)
```

---

## Typography

### Font stack
```
Display / headings:  'Space Grotesk', sans-serif  (weights: 500, 600, 700)
Body / UI:           'Inter', sans-serif            (weights: 400, 500, 600)
Monospace / code:    'IBM Plex Mono', monospace     (weights: 400, 500)
```

All three are loaded from Google Fonts in `<head>`.

### Type scale (inferred from visual analysis)
```
Display (hero number):    48px, 700, Space Grotesk, gold (#f6b73c)
H1 (section heading):     32px, 700, Space Grotesk, #e9ebf2
H2 (card title):          18px, 600, Inter, #e9ebf2
H3 (subsection):          14px, 600, Inter, #cdd2e0
Label (section header):   10-11px, 600, Inter, UPPERCASE, letter-spacing: 0.1em, #6a7088
Body:                     13-14px, 400, Inter, #cdd2e0
Small / meta:             11-12px, 400, Inter, #8c92a6
Mono / code:              12px, 400, IBM Plex Mono, #cdd2e0
Badge text:               10px, 500, IBM Plex Mono or Inter, varies
```

---

## Spacing & Layout

### Overall layout
```
Sidebar width:      235px (fixed left)
Main content:       fluid, fills remaining width
Panel padding:      24px sides, 20px top
Card gap (grid):    16px
Section gap:        24-32px
```

### Sidebar internal spacing
```
Nav item height:      36-40px
Nav item padding:     8px 12px
Nav item gap (icon):  10px
Section label margin: 20px top, 8px bottom
Agent item height:    32px
```

### Cards
```
Border radius:  12px (cards), 8px (inner elements), 6px (badges/pills), 20px (status pills)
Padding:        16-20px
Top accent bar: 2px solid, matches card accent color
Box shadow:     0 1px 3px rgba(0,0,0,0.4)
Glow effect:    radial-gradient in card bg, color matches accent at ~8% opacity
```

### Status pills / badges
```
Padding:        4px 10px
Border radius:  20px (pill)
Font:           11-12px, 500
Structure:      [colored dot 6-8px] [label text]
Border:         1px solid (same color as dot, ~30% opacity)
Background:     color at ~8-12% opacity
```

---

## Component Patterns

### Panel header
```html
<div style="display:flex; align-items:center; justify-content:space-between;
            padding:16px 20px; border-bottom:1px solid rgba(255,255,255,0.07)">
  <div>
    <div style="font-size:10px; font-weight:600; text-transform:uppercase;
                letter-spacing:0.1em; color:#6a7088; margin-bottom:4px">SECTION LABEL</div>
    <div style="font-size:18px; font-weight:600; color:#e9ebf2">Panel Title</div>
  </div>
  <!-- actions (refresh button, etc.) -->
</div>
```

### Metric card
```html
<div style="background:#12161f; border-radius:12px; padding:20px;
            border-top:2px solid #f6b73c; position:relative; overflow:hidden">
  <!-- ambient glow -->
  <div style="position:absolute; top:0; left:0; right:0; bottom:0;
              background:radial-gradient(ellipse at top left, rgba(246,183,60,0.08) 0%, transparent 60%);
              pointer-events:none"></div>
  <!-- content -->
  <div style="font-size:10px; font-weight:600; text-transform:uppercase;
              letter-spacing:0.1em; color:#6a7088; margin-bottom:8px">LABEL</div>
  <div style="font-size:40px; font-weight:700; color:#e9ebf2; font-family:'Space Grotesk'">46</div>
</div>
```

### Status badge / pill
```html
<span style="display:inline-flex; align-items:center; gap:6px;
             background:rgba(45,212,191,0.1); border:1px solid rgba(45,212,191,0.3);
             border-radius:20px; padding:4px 10px; font-size:12px; color:#2dd4bf">
  <span style="width:6px; height:6px; border-radius:50%;
               background:#2dd4bf; box-shadow:0 0 6px #2dd4bf"></span>
  5 running
</span>
```

### Sidebar nav item (active)
```html
<div style="display:flex; align-items:center; gap:10px; padding:8px 12px;
            background:rgba(246,183,60,0.08); border-radius:6px;
            border-left:2px solid #f6b73c; cursor:pointer">
  <!-- icon SVG 16px -->
  <span style="font-size:13px; font-weight:500; color:#e9ebf2">Overview</span>
</div>
```

### Sidebar nav item (inactive)
```html
<div style="display:flex; align-items:center; gap:10px; padding:8px 12px;
            cursor:pointer; border-radius:6px; border-left:2px solid transparent">
  <!-- icon SVG 16px, color:#6a7088 -->
  <span style="font-size:13px; color:#8c92a6">Chat</span>
</div>
```

### Section header label
```html
<div style="font-size:10px; font-weight:600; text-transform:uppercase;
            letter-spacing:0.1em; color:#6a7088; padding:8px 12px 4px; margin-top:16px">
  WORKSPACE
</div>
```

### Hpulse animation (for "live" dots)
```css
@keyframes hpulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50%       { transform: scale(0.5); opacity: 0.4; }
}
/* usage: style="animation: hpulse 1.6s ease-in-out infinite" */
```

### Scrollbar styling
```css
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.09); border-radius: 6px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.18); }
```

---

## Starfield (hero background effect)

The hero "Mission Overview" panel has a canvas-based starfield with:
- ~80-120 tiny particles (1-2px, white/gold tints, low opacity)  
- Slow drift animation
- Subtle warm glow bottom-left + teal glow center-right (radial gradients)
- Background: `#0a0c10` or similar very-dark base

The canvas fills the hero div and is drawn by `ensureStars()` / `drawStars()` in the component JS.

---

## Design Principles (inferred from live UI)

1. **Space / mission control aesthetic** — dark navy, gold accents, cosmic starfield
2. **Data-dense but readable** — small labels, large numbers, clear hierarchy
3. **Color = status** — gold=primary/default, teal=running, green=success, red=blocked, purple=memory
4. **Glow ≠ noise** — glows are subtle (8-12% opacity), used only on key accents
5. **Every panel fills its space** — full-bleed layout, no wasted whitespace
6. **Monospace for IDs/codes** — IBM Plex Mono for agent names, task IDs, timestamps
