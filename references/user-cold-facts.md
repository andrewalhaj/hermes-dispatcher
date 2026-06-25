# User Reference — cold facts offloaded from USER.md

Offloaded 2026-06-16 to reclaim USER.md headroom. These are durable, low-churn reference facts — kept here in full, pointer-ized in USER.md. Pointer in USER.md: `session_search`/this doc.

## DUMMY DATA — never assert as real (2026-06-08)
These were test fixtures / false inferences, explicitly NOT real facts about Andrew:
- **HA entities** Matte, Sanja, Ellie, Jasper = test fixtures (dummy data)
- "Matte" as an alias = false
- Swedish nationality/language = false
- Dearborn / Sterling Heights (MI) locations = false
- 3ds Max (software) = false
- **Occupation: UNKNOWN** — do not infer.

## Hardware detail (canonical live source: references/topology.json)
- **Primary host:** 2018 Mac mini (Macmini8,1, i7-8700B, **15GB RAM**), Ubuntu 24.04 t2-noble, tailnet **100.113.100.81**, `ssh andrew@`, passwordless sudo. macOS WIPED, Ethernet primary. **RUNS Hermes (primary host).**
- **Mac Studio A2901 (M2 Max, 64GB):** free unit, **incoming** as an *add-don't-migrate* local inference node (routine→local Qwen, frontier→Claude). NOT YET LIVE — future plan, not verified present. Routing detail: `session_search "Mac Studio inference routing"`.

For live host/model/profile truth, always prefer `references/topology.json` (verified, drift-checked by whoami-live.sh) over recalled context.
