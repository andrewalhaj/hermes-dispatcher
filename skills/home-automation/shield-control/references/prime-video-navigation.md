# Prime Video Navigation on Shield via ADB — session detail

Task: "Launch prime video and play vox machina season 1 episode 1." Outcome: Prime
launched and the title reached, but S1E1 was NOT cleanly started — left on detail page
for the user to finish the last 3 clicks after blind navigation kept mis-resolving.
This file captures the exact traps so a future session goes straight.

## Package discovery (the launch worked, the discovery commands lied)

```
pm list packages | grep -iE 'amazon|prime|video'
  package:com.amazon.amazonvideo.livingroom.nvidia   <- DUMMY, enabled=0
  package:com.amazon.amazonvideo.livingroom          <- REAL, enabled=1
```

- `monkey -p com.amazon.amazonvideo.livingroom 1` → "No activities found to run, monkey aborted."
- `monkey -p com.amazon.amazonvideo.livingroom.nvidia 1` → same.
- `cmd package resolve-activity --brief <either>` → "No activity found".
- `cmd package query-activities ... LEANBACK_LAUNCHER | grep amazon` → only surfaced
  `com.amazon.music.tv`, NOT Prime Video.

What actually worked — read the package dump for the resolver table:
```
dumpsys package com.amazon.amazonvideo.livingroom | grep -iE "enabled=|Activity"
  com.amazon.amazonvideo.livingroom/com.amazon.ignition.IgnitionActivity filter ...
  User 0: ... enabled=1 ...
```
Then launch explicitly:
```
adb -s 100.69.145.58:5555 shell am start -n com.amazon.amazonvideo.livingroom/com.amazon.ignition.IgnitionActivity
```
(If already running it returns "Warning: Activity not started, ... brought to the front"
or "intent has been delivered to currently running top-most instance" — both fine, app is foregrounded.)

`enabled=0` on the `.nvidia` variant ≠ disabled-by-user — it's the "default" tri-state, but
it has no launchable activity regardless. Use the base package.

## The three navigation traps (all verified by screenshot this session)

### 1. Play defaults to RESUME the current season
User was mid-Season 4. Detail page Play button read **"Resume S4 E1"**. There is no
"start from S1" button — you must change the **season selector dropdown** (bottom-left of
the detail page, reads "Season 4") to Season 1, then pick Episode 1 from the episode row.

### 2. Center-press resolves to Play, not "open dropdown"
Repeatedly, trying to open the season dropdown, the center-press instead started S4 E1
playing (confirmed by subtitle text appearing on a black screen, e.g. a Grog song lyric).
Root cause: focus was on the Play column / episode tile, not the dropdown. The dropdown sits
just ABOVE the episode thumbnail row; one DPAD_DOWN too many lands on the S4 E1 tile and
center = play. Fix: after moving, screenshot and confirm the dropdown element itself shows a
focus highlight (darker/outlined) BEFORE pressing center. Backed out of accidental playback
with KEYCODE_BACK (sometimes 2× — once raised an "Exit the application" OK/Cancel dialog;
DPAD_DOWN to Cancel, center, to stay in-app).

### 3. Hero carousel auto-rotates
On the home screen, the featured hero banner cycled on its own:
Vox Machina (Resume) → Kill Blue → a BritBox period-drama promo → back. A DPAD_RIGHT meant
to move from Resume to "More details" instead landed on a different show because the banner
had rotated. A `--longpress KEYCODE_DPAD_CENTER` on the hero (intending the title's options
menu) launched "The Pout-Pout Fish" because the carousel had moved. Lesson: do not navigate
off the home hero by feel. Go LEFT into the sidebar and use **search** for a stable path.

## Sidebar search path (deterministic)
- DPAD_LEFT repeatedly to enter the left rail, DPAD_UP to the top = magnifying-glass search icon.
- Screenshot-confirm the search icon is focused, center-press to open the search field.
- `KEYCODE_SEARCH` does NOT do this — it opens the Shield SYSTEM Google Assistant voice UI
  ("Ask me a question, or try a suggestion" with Open Netflix / What's the weather chips).
  That is the wrong surface; back out and use the in-app sidebar search icon instead.

## Vision-model caveat
The fallback vision model did NOT recognize Plex's or Prime's TV layouts by name (called Plex
"not Plex", called a Prime detail page "Apple TV"). Trust the structural read (tabs, buttons,
focus highlight, S/E labels) over its product-name guess. `dumpsys window | grep mCurrentFocus`
is the authoritative signal for which app/activity is foreground.
