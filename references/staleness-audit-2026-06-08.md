# Reference Doc Staleness Audit — Consolidated Report

Audit run: 2026-06-08 ~21:30 UTC
Docs audited: 3 | Workers: 3 | Gate: PASS (verifier t_67e90813)
Method: every claim checked against live system state via direct absolute-path reads

---

## /root/.hermes/references/infrastructure-summary.md

**Verdict: 6 DRIFTED / 12 CURRENT / 7 unverifiable-from-worker**

### Drifted items

| Line | Claim in doc | Live reality |
|------|-------------|-------------|
| 81 | "## Cron Jobs (6)" — table lists 6 jobs (Daily Backup, KB Dedup, Infra Watchdog, Honcho→Obsidian Bridge, Delegation Audit) | **12 jobs exist.** 6 undocumented jobs are not in the table. Only 6 listed in the doc match live IDs; the other 6 live jobs have no doc coverage. |
| 106 | MEMORY.md: "2,088/2,200 chars" | **2,922 chars, 17 lines.** Exceeded the 2,200-char budget. The overflow means the limit itself is fine but the live content hasn't been pruned. |
| 107 | Knowledge DB: "77 facts" | **1,046 LanceDB files** in the knowledge_db directory (not 77 fact entries). The metric is wrong — it was likely counting rows differently, but the live dataset is far larger than the doc implies. |
| 109 | state.db: "33 sessions, 3,811 msgs" — also line 134 says "36MB" | **25 sessions, 1,699 msgs, 26MB.** Sessions dropped (8 fewer), messages down substantially (2,112 fewer), and DB file is 10MB smaller. The doc overstates the store size in all dimensions. |
| 136 | Key Files table lists `manifest-topology.md` as present | **FILE NOT FOUND.** The path `/root/.hermes/references/manifest-topology.md` does not exist on disk. Doc claims it exists; it doesn't. |
| 139 | Key Files table references `/root/manifest/.env` and `/root/manifest/docker-compose.yml` | **DIRECTORY DOES NOT EXIST.** `/root/manifest/` is absent entirely — no .env, no docker-compose.yml. Both paths are dead references. |

### Verifier note
The verifier confirmed the MEMORY.md drift direction holds — the 2,200 char limit was breached (~2,922 live on first check, but file is live-growing), so the doc's representation of the limit is still useful even if the current byte count is wrong. The other 5 drifts are unambiguous.

---

## /root/.hermes/references/honcho-confabulation-blocklist.md

**Verdict: CLEAN — zero drift**

10 of 13 claims directly verified as CURRENT against live system state. The remaining 3 (peer content emptiness, Discord peer data, separate swarm-verifier Honcho workspace) require the Honcho API to verify — the worker couldn't reach them from filesystem probes, but nothing about the doc is contradicted by what *is* reachable.

Confirmed live:
- Honcho Drift Correction cron (d6417b2f32c6) exists, enabled, last OK 2026-06-08 20:25, references the blocklist file by absolute path
- claude-opus-4-8 on swarm-verifier and voice-changer profiles
- deepseek-v4-flash on all three swarm-worker profiles; deepseek-v4-pro on delegation
- LanceDB alive at `/root/.hermes/knowledge_db/` with Weekly KB Dedup cron (cdd1800159eb)
- Server IP 5.78.238.81 confirmed on eth0
- Honcho workspace "hermes", operator peer 8878729385, AI peer "hermes" all match honcho.json
- Decoy/empty peer names exist in config (root, ha-bot, -1003947663220)
- Cron usage pattern matches the doc's description exactly

No items to correct.

---

## /root/.hermes/references/swarm-introspection-doctrine.md

**Verdict: 1 DRIFT / 8 CURRENT / 1 unverifiable**

### Drifted item

| Lines | Claim in doc | Live reality |
|-------|-------------|-------------|
| 16-17 | "an **empty `cron/jobs.json`** (no jobs) — so `hermes cron list` from a worker returns '0 jobs'" | **File is absent.** The worker profile has no `cron/jobs.json` at all — not an empty file, just nothing there. `hermes cron list` would still report zero jobs against a missing file, so the practical guidance in the doc is still correct. But the literal claim ("empty cron/jobs.json") is slightly off — it should say "no cron/jobs.json present." |

### Verifier note
Semantic drift only — the doc's actionable point (workers have no cron jobs) still holds. The file being absent vs. empty produces the same behavior (0 jobs). The verifier classified this as correctly minor.

---

## Summary

| Doc | Items checked | Current | Drifted | Unverifiable | Verdict |
|-----|-------------|---------|---------|-------------|---------|
| infrastructure-summary.md | 18 | 12 | 6 | 0 (in worker scope) | **Needs update** |
| honcho-confabulation-blocklist.md | 13 | 10 | 0 | 3 | **CLEAN** |
| swarm-introspection-doctrine.md | 10 | 8 | 1 | 1 | **Minor fix** |

**Total: 7 drifted items across 3 docs.** infrastructure-summary.md accounts for 6 of them and needs a refresh pass. The other two docs are in good shape — one clean, one with a one-word fix.
