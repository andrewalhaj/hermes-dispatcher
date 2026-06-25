# Mini + Studio Hardening — Session State
*Parked: 2026-06-17*

## What was done this session

### Mac mini RAM upgrade
- Upgraded to 32GB (2×16GB DDR4 @ 2667 MT/s) — confirmed live via `free -h` + `dmidecode`
- Memory updated in USER.md

### Cron job routing fixes
All `deliver: origin` jobs were firing into the Andrew DM. Fixed:

| Job | Fix |
|---|---|
| Mac Studio Ollama Watchdog (`223e51b1abd6`) | Script path `scripts/studio-watchdog.sh` → `studio-watchdog.sh`; deliver → cron group |
| Session Distill (`18ba6ea06795`) | deliver: origin → local |
| Memory Headroom Watchdog (`26b23776360b`) | deliver: origin → local |
| Skill desc cliff watchdog (`38efb0814181`) | deliver: origin → local |

### Studio model roster (as of this session)
- `qwen2.5-128k` — 47GB — text / delegation / cron
- `qwen2.5vl:7b` — 6GB — vision
- `llava-llama3` and `qwen2.5:72b` removed (~53GB freed)

### Studio config
- LaunchAgent installed: `com.ollama.server.plist` in `~/Library/LaunchAgents/` (survives reboots)
- GPU wired limit raised to 56GB (`iogpu.wired_limit_mb=57344`)
- Sleep disabled: `pmset` + `systemsetup`
- Passwordless sudo: `/etc/sudoers.d/localadmin-nopasswd`

## Open items / what to pick up next
- Several cron jobs showing `last_status: error` — notably Memory Offload (default + ha-bot), Memory Honcho Dedup (both profiles), Honcho Drift Correction, Daily Knowledge Capture — all using `qwen2.5:72b` model name which may need updating to `qwen2.5-128k` now that 72b was removed from Studio
- Daily Delegation Audit delivering to `-1003947663220` (cron group) — verify that's still the right target
- Studio Ollama Watchdog was erroring — will self-clear next 15m run now that path is fixed
