# Delegation Audit Archive — June 2026

_Archived 2026-06-06 22:59 UTC. These are CLOSED post-mortems from the Daily Delegation Audit, moved out of pending-fixes.md. Entries 1-7 diagnose the 15-session Manifest/OAuth debugging marathon (Manifest decommissioned 2026-06-05 — problem domain gone). Entry 8 is the Skill-Memory marathon post-mortem. The file's top-level Recommendation (a hard delegation-checkpoint guard at 50 terminal + 80K tokens) was IMPLEMENTED 2026-06-06 as ~/.hermes/patches/delegation_checkpoint.py + the Patch Guard Self-Heal cron. No action remains in any archived entry._

---

## 2026-06-05 - Home Assistant Dashboard with TV Calendar Weather (Original)
- Violation: >100K input tokens (1,101,936) + zero delegate_task; >15 terminal calls (91) without delegation
- Root cause: Multi-domain task sprawl — started as HA dashboard build, evolved into Manifest Docker debugging, Anthropic OAuth troubleshooting, claude-oauth-proxy installation, DB schema inspection, and token lifecycle management. All work done inline through 91 sequential terminal calls in a single session with 289 messages. No sub-task was carved off even when the scope clearly fractured into independent workstreams (docker manipulation, OAuth debugging, proxy setup).
- Fix: Split into 3 delegate_task calls: (1) "Install and configure claude-oauth-proxy on host, test with existing token" — docker/install work, (2) "Debug Manifest's Anthropic provider auth: check DB schema, auth_type flags, test API calls" — DB/infra probing, (3) "Build HA dashboard components" — the actual original goal. Each sub-agent gets a self-contained spec and bounded context, preventing the 1.1M token accumulation.
- Estimated savings: ~$40-50 (50-60% of $83.46 cost), ~500K-600K input tokens avoided

## 2026-06-05 - Home Assistant Dashboard with TV Calendar Weather #2
- Violation: >100K input tokens (173,005) + zero delegate_task; >15 terminal calls (132) without delegation
- Root cause: Gateway-shutdown resume incurred large context restoration cost (~16K tokens just for the system note + rollup). The resumed session then continued Manifest/OAuth debugging with 132 sequential terminal calls. Pure inline execution — docker exec, node inline scripts, curl probes, log grepping — all chained in a single conversation loop. No attempt to extract the manifest-auth debugging into a sub-agent.
- Fix: After gateway-shutdown resume, delegate the Manifest auth configuration task: "Configure Manifest to use claude-oauth-proxy as Anthropic provider: set base_url, inject token, verify models load" — a self-contained 10-minute sub-agent task.
- Estimated savings: ~$0.10-0.15 (40-50% of $0.25 cost), ~70K input tokens avoided

## 2026-06-05 - Home Assistant Dashboard with TV Calendar Weather #3
- Violation: >100K input tokens (166,656) + zero delegate_task; >15 terminal calls (103) without delegation
- Root cause: Another gateway-shutdown resume cycle. Continued inline Manifest debugging with 103 terminal calls — docker exec loops, container log inspection, OAuth flow retries. Zero delegation despite repeated patterns of "check logs → modify config → restart → check logs."
- Fix: Delegate the entire "Manifest Anthropic OAuth loop" as a background task: "Monitor manifest logs, retry OAuth exchange when rate limit clears, confirm token storage, verify model discovery." The retry loop pattern is ideal for delegation — bounded, repeatable, no user interaction needed.
- Estimated savings: ~$0.08-0.12, ~65K input tokens avoided

## 2026-06-05 - Home Assistant Dashboard with TV Calendar Weather #9
- Violation: >100K input tokens (101,331) + zero delegate_task; >15 terminal calls (118) without delegation
- Root cause: Continued Manifest/OAuth proxy work with inline terminal-heavy debugging. Session accumulated 118 terminal calls across docker, curl, npm, and filesystem operations. The work had fractalized into multiple parallel threads (proxy config, docker networking, API testing) but everything remained serialized in one conversation.
- Fix: Parallel delegate_task batch: (1) claude-oauth-proxy health check and token validation, (2) Manifest provider configuration update, (3) End-to-end test: call Manifest's chat completions endpoint through the proxy chain. Three parallel sub-agents with clear acceptance criteria.
- Estimated savings: ~$0.08-0.10, ~40K input tokens avoided

## 2026-06-05 - Home Assistant Dashboard with TV Calendar Weather #12
- Violation: >15 terminal calls (133) without delegation (95K input tokens, under 100K threshold for pattern 1)
- Root cause: Heaviest terminal session — 133 tool messages. Work included browser automation (browser_navigate), web extraction, file patching, and extensive terminal debugging. The session included skill management operations (skill_view, skill_manage, skills_list) mixed with terminal work — a clear signal that the session was context-switching between learning mode and doing mode.
- Fix: Separate learning from doing. Delegate the terminal-heavy Manifest/proxy configuration work while keeping skill research lightweight. A single delegate_task: "Verify claude-oauth-proxy → Manifest → Anthropic chain: configure, test, report" would remove ~80 terminal calls from the main context.
- Estimated savings: ~$0.10-0.15, ~50K input tokens avoided

## 2026-06-05 - Home Assistant Dashboard with TV Calendar Weather #14
- Violation: >100K input tokens (344,312) + zero delegate_task; >15 terminal calls (65) without delegation
- Root cause: Accumulated context from 14 sequential sessions on the same topic without any delegation. Each gateway-shutdown resume added another ~16K token context restoration cost. The session continued Manifest/OAuth proxy work with browser automation (browser_navigate, browser_vision) layered on top of terminal debugging.
- Fix: After 3+ sessions on the same problem without resolution, the AGENTS.md delegation rule should have triggered ("Same command fails 3+ times → STOP and delegate"). The entire "Make Manifest work with Claude Max via OAuth proxy" task should be a self-contained sub-agent spec with a 30-minute timeout and clear pass/fail criteria.
- Estimated savings: ~$0.25-0.35, ~140K input tokens avoided

## 2026-06-05 - Home Assistant Dashboard with TV Calendar Weather #15
- Violation: >100K input tokens (209,062) + zero delegate_task; >15 terminal calls (81) without delegation
- Root cause: 15th consecutive session on the same problem thread. Context compaction occurred (msg#11671 shows "[CONTEXT COMPACTION — REFERENCE ONLY]") indicating the conversation had grown too large for the context window. 81 more terminal calls were executed inline: OAuth PKCE verification, token exchange debugging, Cloudflare JA3 fingerprinting workarounds.
- Fix: This session was beyond the delegation tipping point. Should not have been started inline at all — the compacted context note should have triggered a delegate_task with the summary: "Resolve the remaining Manifest OAuth chain: claude-oauth-proxy works, Manifest sends x-api-key instead of Bearer. Options: (a) patch Manifest to use Bearer, (b) configure proxy to accept x-api-key, (c) use direct API key fallback. Implement the simplest working option."
- Estimated savings: ~$0.12-0.18, ~80K input tokens avoided

---

## Summary

**Pattern:** The "Home Assistant Dashboard" task fractured into a 15-session, ~$85+ Manifest/OAuth debugging marathon spanning 12+ hours with zero effective delegation. Sessions #4 and #5 each had 1-2 delegate_task calls (the exception proving the rule — they still had 45-118 terminal calls, showing delegation was token rather than structural).

**Root systemic issue:** Three AGENTS.md delegation triggers were missed:
1. ">3 HA restarts → delegate" — NO: this was >15 docker exec/inspect/restart cycles
2. "Same command fails 3+ times → STOP and delegate" — the OAuth exchange was retried across 6+ sessions
3. "Multi-system probing → parallel delegate_task" — docker + DB + network + proxy = 4+ systems

**Recommendation:** Add a hard guard: any session exceeding 50 terminal calls AND 80K input tokens with zero delegate_task calls should auto-prompt a delegation checkpoint before continuing.

## 2026-06-06 - Skill Memory Across Sessions
- Violation: >100K input tokens (231,628) + zero delegate_task; >15 terminal calls (98) without delegation
- Root cause: Marathon session spanning ~16 hours with 24 user messages across 10+ distinct, independent task domains (skills/memory Q&A, Sonos HA troubleshooting, cron health check, architecture efficiency review, Govee review, infra-as-code question, Plex/Prime Video media control, Zapier connection setup, LG ThinQ appliance onboarding). All work serialized inline — 98 terminal calls accumulated in a single conversation, including 20+ SSH probes into the remote backup host for Sonos debugging. No task was carved off despite clear independence boundaries. The session accumulated $24.20 in cost entirely from inline execution.
- Fix: Split into 4 delegate_task calls: (1) "Diagnose and fix Sonos-HA connectivity: verify Tailscale subnet routing, test speaker reachability from HA container, apply config fix (advertise_addr) and restart" — the SSH-heavy debugging (~20 terminal calls), (2) "Architecture efficiency review: profile primary/backup hosts, check memory/disk/swap, recommend optimizations" — the system profiling work (~15 terminal calls), (3) "Connect Zapier MCP: configure webhook, test Gmail/Calendar integration" — the Zapier work, (4) "Research and configure LG ThinQ for Home Assistant: validate API token, add washer/dryer to HA dashboard" — the appliance onboarding. Each sub-agent gets a self-contained goal, preventing 231K token accumulation in main context.
- Estimated savings: ~$10-15 (40-60% of $24.20 cost), ~90K-140K input tokens avoided
