# System Inventory — canonical subsystem list for health_audit.py

**Purpose:** The audit checks THIS list, not "what the agent remembered." Adding a subsystem here is what makes it monitored. An unlisted subsystem is an invisible subsystem — if you build something new, add a row here or the audit will never know to check it.

**Probe contract:** every subsystem defines a FUNCTIONAL probe (proves it *works*, not that it *exists*) and an `expect` (what a healthy result looks like). Result states: `PASS` / `FAIL` / `UNVERIFIABLE` (probe couldn't run or capability absent — surfaced loudly, never silently dropped).

| id | subsystem | functional probe | expect (PASS) |
|----|-----------|------------------|---------------|
| gateway | Hermes gateway | `systemctl --user is-active hermes-gateway` | `active` |
| bypass | Anthropic OAuth bypass | bypass auth self-test | `AUTH TEST OK` + `_HEAVY_MODEL=claude-opus-4-8` |
| bfull_recall | B-full auto-RAG QUALITY | `knowledge.py` search `"wall-dash dashboard"` | known wall-dash doc in results, top hit score ≥0.80 |
| bfull_golden | B-full patch integrity | injection golden substring present in live run.py | `True` |
| patch_guard | patch_guard drift | dry-run `--check` | silent, exit 0 |
| codegraph_mcp | CodeGraph MCP wiring | `hermes mcp test codegraph` parse `Tools discovered: N` | N > 0 (4 when daemon warm; 0 on cold first-call, self-heals) |
| codegraph_fresh | CodeGraph index freshness | compare index commit vs `git -C /usr/local/lib/hermes-agent rev-parse HEAD` | match, else FAIL (stale) |
| delegation | DeepSeek delegation | live API probe (HTTP status) | 200 |
| knowledge_rows | Knowledge store | `knowledge.py` stats — fact count | > 0, non-decreasing vs last run |
| web_stack | Self-hosted web (searxng/firecrawl/camofox) | HTTP probe each container | all 200 |
| cron | Cron scheduler | scheduler alive + jobs fired recently | enabled count matches, recent fire timestamp |
| memory_headroom | Memory store saturation | `wc -m` each store vs LIVE cap from config.yaml | both < 90% |
| topology | Host topology drift | `whoami-live.sh` diff vs topology.json golden | no drift |
| honcho | Honcho connectivity | peer card fetch | responds non-empty |

## Notes
- **codegraph_mcp** VERIFIED 2026-06-16: serves 4 tools when its daemon is warm; a cold first-call (no daemon, e.g. post-restart) returns 0 then self-heals. The audit reads the live count — a transient 0 means "daemon cold," not "broken." Earlier "cwd bug" hypothesis was wrong and has been corrected.
- **UNVERIFIABLE is a feature.** If a probe can't run (capability missing, timeout), it reports UNVERIFIABLE — never silently PASS. A green run means "every listed check verified working," not "nothing errored."
- Read the LIVE cap for `memory_headroom` from config.yaml, never the injected header.
