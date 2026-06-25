# Hermes Infrastructure Summary (VERIFIED 2026-06-16)

> **Why this exists:** Context compaction kills in-memory infrastructure knowledge. This file is the durable reference. Read it at session start or whenever topology questions arise. Companions: `swarm-introspection-doctrine.md`, `honcho-confabulation-blocklist.md`, `scheduler-recovery-procedure.md`.
>
> **2026-06-16 rewrite:** Hermes was MIGRATED off Hetzner `hil-1` onto the local **andrew-Macmini** (2018 T2 Intel Mac mini). The prior version of this doc described the Hetzner worker box as primary compute — that is STALE. Hermes now runs locally on the Mac mini; `hil-1` was repurposed to host Mealio. Also corrected: profile roster (3, not 10), cron count (20, not 12), LanceDB row count.
>
> **Earlier (2026-06-08):** the Manifest + Railway PostgreSQL + nginx-LB + PRIMARY/BACKUP architecture was DECOMMISSIONED 2026-06-05. That stack is gone; routing is direct-to-provider.

---

## Servers

| | PRIMARY (Hermes host) | HA HOST | MEALIO HOST |
|---|---|---|---|
| **Hostname** | `andrew-Macmini` | `ubuntu-2gb-ash-1` | `ubuntu-8gb-hil-1` |
| **Public IP** | `68.34.49.223` (Comcast residential) | `178.156.246.115` | `5.78.238.81` |
| **Tailscale** | `100.113.100.81` | `100.119.118.54` | `100.64.150.51` |
| **Spec** | 2018 T2 Mac mini, i7-8700B, 15GB RAM, x86_64 (32GB upgrade pending) | 2GB | 8GB Hetzner |
| **OS** | Ubuntu 24.04 `t2-noble` | — | Ubuntu |
| **Runs** | Hermes agent + ALL gateways + all cron + session DB + Supabase + web stack (SearXNG/Firecrawl/Camofox) | Home Assistant core + wall-dash (nginx :5051) | Mealio (Next.js :3015, CF tunnel) |
| **Role** | Primary compute / orchestration (runs locally on the home network) | **Production HA — NOT a backup** | Mealio recipe app |
| **SSH** | Local (runs here) | `root@178.156.246.115`, key `~/.ssh/id_ed25519` | via tailnet |

**Key facts:**
- **Hermes runs ON the local Mac mini** (`andrew-Macmini`, tailnet `100.113.100.81`), exiting via the home Comcast residential IP `68.34.49.223`. `ssh` to self is unnecessary; run locally. This is NOT Hetzner anymore.
- `178.156.246.115` / tailnet `100.119.118.54` is the **production Home Assistant host**, kept separate for blast-radius isolation. NOT a backup/standby.
- `hil-1` (Hetzner 8GB, tailnet `100.64.150.51`) was the OLD Hermes worker box — now **repurposed to host Mealio** (`:3015`). It is NOT running Hermes anymore.
- There is no Manifest, no Railway, no nginx load-balancer, no PRIMARY/BACKUP Hermes pair. Routing is direct-to-provider.

## Model Routing (direct, non-Manifest)

| Role | Model | Provider | Notes |
|---|---|---|---|
| Main (this agent, `default`) | `claude-sonnet-4-6` | Anthropic | OAuth bypass (hermes-claude-auth); auto-upgrades to `claude-opus-4-8` on complex tasks |
| Delegation (subagents) | `deepseek-v4-pro` | DeepSeek | direct, `DEEPSEEK_API_KEY`; max_concurrent_children=8, max_spawn_depth=1 |

**Anthropic auth:** Claude Max via `hermes-claude-auth` OAuth bypass — a `sitecustomize.py` import hook loading `~/.hermes/patches/anthropic_billing_bypass.py`. No proxy, no Manifest. Credentials at `~/.claude/.credentials.json`.

## Profiles (3 live)

- **Active (3):** `default` (me/orchestrator, Sonnet 4.6 → Opus 4.8 on complex), `executor` (general, DeepSeek), `ha-bot` (HAJarvis @HAjarviss_bot, Anthropic)
- The kanban swarm pod profiles (`swarm-worker-a/b/c`, `swarm-verifier`, `swarm-synthesizer`) and `voice-changer` described in older notes are NOT present on this host — do not assume them. `voice-changer` was DECOMMISSIONED 2026-06-09. Verify with `ls ~/.hermes/profiles/` before assigning cross-profile work.

## Kanban Swarm

- `dispatch_in_gateway: true` → BOUNDED-AUTONOMOUS: gateway tick auto-claims+spawns ready workers within the cap. Safety = verifier gate + cap + timeouts, NOT per-action approval.
- **Autonomy grant (Andrew, 2026-06-08):** swarm dispatch for read/analysis work is autonomous within bounds — the agent dispatches as it deems fit without per-task approval. Infra MUTATIONS (config/profile/skill/cron writes, systemctl/docker, remote hosts) still gate.
- Dispatch + introspection doctrine + verify-against-ground-truth: skill `kanban-swarm-dispatch`; full doctrine `~/.hermes/references/swarm-introspection-doctrine.md`.
- **Worker introspection gotcha:** FS is shared (absolute-path reads work) but worker profiles have OWN empty cron/state.db + no references/ — so profile-scoped `hermes` subcmds / relative paths give false "missing." Always pass ABSOLUTE paths in introspective swarm prompts.

## Gateway Management

| Action | Command |
|---|---|
| Status | `hermes gateway status` (or `systemctl --user status hermes-gateway`) |
| Restart | **detached** (see below) |
| Logs | `journalctl --user -u hermes-gateway --no-pager -n 50` |

**CRITICAL:** USER-scoped systemd unit (`~/.config/systemd/user/hermes-gateway.service`). Plain `systemctl restart hermes-gateway` (system scope) fails with "Unit not found" — always `--user`.

**Restart deadlock + fix:** `hermes gateway restart` SELF-BLOCKS from inside a gateway session (anti-loop guard), and the controlling turn IS the in-flight work the gateway drains on SIGTERM — so an in-turn restart deadlocks. Use a detached out-of-cgroup timer, then end the turn:
```bash
systemd-run --user --on-active=2 --unit=hermes-gw-reload systemctl --user restart hermes-gateway
```
`Restart=always`, `TimeoutStopUSec=3min30s` are the safety net. Full pattern: `hermes-maintenance` skill §2.

## Cron Jobs (20)

| Job Name | Schedule | Type | Delivers |
|---|---|---|---|
| Daily Knowledge Capture | `30 2 * * *` | agent (deepseek) | local |
| Daily Hermes Backup | `0 3 * * *` | no_agent | local |
| Weekly KB Audit (dedup + pointer coverage) | `0 4 * * 0` | no_agent | TG+Discord |
| Patch Guard Self-Heal | `0 5 * * *` | no_agent | TG+Discord |
| Parallel.ai Re-exposure Watchdog | `0 5 * * *` | no_agent | TG+Discord |
| Monthly Cold-Store Staleness Audit | `0 5 1 * *` | agent | local |
| Honcho Drift Correction | `30 6 * * *` | agent | local |
| Memory Honcho Dedup | `0 7 * * *` | agent (deepseek) | TG+Discord |
| Memory Honcho Dedup (ha-bot) | `30 7 * * *` | agent | TG+Discord |
| Memory Dedup Audit | `0 8 * * 0` | agent (deepseek) | TG+Discord |
| Memory Dedup Audit (ha-bot) | `30 8 * * 0` | agent | TG+Discord |
| Honcho-to-Obsidian Bridge | `0 8 * * *` | no_agent | local |
| Daily Delegation Audit | `0 9 * * *` | agent (deepseek) | TG+Discord |
| Swarm Proving Ground — Reference Staleness Audit | `0 10 1,15 * *` | agent | local |
| Memory Offload (default) | `0 * * * *` | agent | local |
| Memory Offload (ha-bot) | `0 * * * *` | agent | local |
| Skill description cliff watchdog | `0 */6 * * *` | no_agent | TG+Discord |
| Infra Watchdog (15-min) | `*/15 * * * *` | no_agent | TG+Discord |
| Infrastructure Change Watchdog | `every 5m` | no_agent | TG+Discord |
| Kanban Dashboard Export | `every 5m` | no_agent | local |

Cron alerts → Telegram Cron Jobs channel `-1003947663220` (+ Discord #cron-jobs), NOT DM. Silent-by-default watchdogs alert only on a manual-intervention event.

## Memory System (4 layers)

> **Recall precedence (reordered 2026-06-09 — lean toward Supabase):** the deterministic cold store is now the PRIMARY per-turn injected memory; Honcho is SECONDARY (on-demand user-modeling, no longer dominates every turn). The two inject independently — there is no shared pipeline or fallback between them.

| # | Layer | Backend | Location | Role | State (2026-06-09) |
|---|---|---|---|---|---|
| 1 | Hot | curated MEMORY.md | `~/.hermes/memories/MEMORY.md` | every-turn behavioral facts | ~2,365 / **3,000** chars |
| 2 | **Knowledge (PRIMARY recall)** | Supabase + **B-full** per-turn auto-RAG | `~/.hermes/knowledge_db/` | deterministic fact injection, score ≥0.80 | 419 rows (2026-06-16) |
| 3 | **Person (SECONDARY)** | Honcho (cloud dialectic) | workspace `hermes`, operator peer `8878729385` | on-demand user-modeling | cloud → Obsidian daily |
| 4 | Warm/Cold | Obsidian vault | Obsidian | archive only (thin by design post-Honcho) | archive |

- **Retrieval Strategy: B-full (LIVE, core patch in `gateway/run.py`).** Per-turn auto-RAG: searches the cold store every turn, injects hits ≥0.80. Tuned 2026-06-09 to `top_k=5, max_chars=1000` (raised from 3/600 to elevate deterministic recall). Protected by `_heal_bfull` in Patch Guard. B-lite (agent-invoked search) remains the manual fallback. NOT B-lite-only anymore.
- **Honcho leaned down 2026-06-09** (`config.yaml` `honcho:`): `injectionFrequency: first-turn` (was every-turn), `reasoningLevelCap: low` (was high), `dialecticCadence: 3`. Honcho still owns user-modeling but no longer auto-injects every turn — read the curated card on demand via `honcho_profile(peer="8878729385")`.
- **Honcho topology:** workspace `hermes` (NOT default); operator peer `8878729385` (curated card); AI peer `hermes`; `root` peer EMPTY (the `peer="user"` alias mis-resolves to it in isolated/cron sessions — pin `8878729385`).
- **Drift defense:** `_format_first_turn_context` patched to drop the dirty dialectic representation + derived user card from injection (keeps summary + AI card); protected by Patch Guard Self-Heal; `Honcho Drift Correction` cron re-asserts the clean card at 06:30. Blocklist: `honcho-confabulation-blocklist.md`.

### Query/update Knowledge tier
```bash
python3 ~/.hermes/scripts/knowledge.py search "query"
KNOWLEDGE_TAGS="tag1,tag2" KNOWLEDGE_PRIORITY="high" python3 ~/.hermes/scripts/knowledge.py store "fact"
```

## Config write guard

`config.yaml` `patch`/`write_file` are BLOCKED (prompt-injection defense — guard stays ON, see Perseus-repo rejection). Use `hermes config set <key> <value>`. `.env` `read_file`/`write_file`/`patch` also blocked — use terminal/Python line-edits (never `sed -i` on `.env`).

## Hard-Learned Lessons (DON'T REPEAT)

1. **Filesystem is ground truth.** Stale notes/injected summaries lie. Probe live state before asserting — this session alone, notes wrongly claimed LanceDB "never installed" (165 rows live) and swarm models "auto" (explicitly flash/opus).
2. **Gateway is user-scoped systemd.** `--user` mandatory; restart must be detached (deadlock above).
3. **Durable files beat memory.** Context compacts silently. Write findings to `~/.hermes/references/`.
4. **Honcho dirty injection is re-derived, not stored** — counter-evidence + the format patch are the levers; there is no delete-observation API.
5. **Swarm workers see a shared FS but their own empty profile stores** — pass absolute paths for introspection; never cwd-align (breaks state.db isolation).
6. **Memory char edits:** read the live file, make ONE precise edit; don't guess-and-trim against the cap.

## Key Files Reference

| File | Purpose |
|---|---|
| `~/.hermes/config.yaml` | Hermes config (model, providers, delegation, tools) |
| `~/.hermes/.env` | API keys (DEEPSEEK_API_KEY, HONCHO_API_KEY, etc.) |
| `~/.hermes/cron/jobs.json` | All cron job definitions |
| `~/.hermes/state.db` | Session + message store (SQLite, ~118MB) |
| `~/.hermes/knowledge_db/` | Supabase semantic knowledge base (419 rows, 2026-06-16) |
| `~/.hermes/memories/MEMORY.md` | Hot curated memory (3,000-char cap) |
| `~/.hermes/references/swarm-introspection-doctrine.md` | Swarm dispatch doctrine |
| `~/.hermes/references/honcho-confabulation-blocklist.md` | Honcho drift blocklist + topology |
| `~/.hermes/references/scheduler-recovery-procedure.md` | Disaster recovery |
| `~/.hermes/patches/anthropic_billing_bypass.py` | OAuth bypass + complexity classifier |
| `~/.hermes/scripts/patch_guard.py` | Self-heal watchdog (bypass, deleg, honcho format patch) |
