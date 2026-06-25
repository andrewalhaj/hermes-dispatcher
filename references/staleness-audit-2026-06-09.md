# Cold-Store Staleness Audit — 2026-06-09

Method: knowledge-store skill §Staleness Audit (deterministic dead-term scan → live-premise verify → 4-bucket classify). Read-only; mutations below are GATED, awaiting greenlight.

**Store state:** 170 rows. Full-row backup: `references/_archive/lancedb-full-20260609-233532.json` (verified 170 rows).
**Built-in stale-check:** 0 stale facts (30d threshold).
**Age profile:** 118 rows <7d, 52 rows 7–30d, 0 rows >30d.

## Dead-term scan results (7 patterns, verified-dead premises)

| Row | Hit | Bucket | Action |
|-----|-----|--------|--------|
| 71185125 | "HA dashboard is ha-fusion at :5050" (high prio) | **CORRECT** — stale current-state claim; wall-dash :5051 is live | Rewrite in place (GATED — proposed below) |
| 8c342769 | "ha-fusion FULLY SCRUBBED 2026-06-08" | PROTECT-meta — asserts the death, that's its job | Keep |
| 6d5a363a, f438e831, df7f4f58 | "manifest-vision" in delegation-transport post-mortem chunks | KEEP-historical — true record of past event | Keep |
| (zapier/voice-changer/sonnet-default/ElevenLabs patterns) | 0 hits | — | — |

## Mutations EXECUTED 2026-06-09 23:42 (greenlit by Andrew, "address the cold store audit")
- **71185125 (stale ha-fusion row): deleted + re-stored corrected** as `830a367f` [high, tags: wall-dash/ha-dashboard/infrastructure/deploy] — delete-and-restore used (not in-place edit) so the embedding vector matches the corrected text. Retrieval verified: "HA dashboard wall-dash port" → 0.9104 top hit.
- **e21c3d81 (1.000-similarity duplicate): deleted.** It was the OLDER chunk (infrastructure-summary.md "Hard-Learned Lessons" section, ingest of Jun 04 "VERIFIED 2026-06-03" version); kept `48cf72f3` (Jun 08 ingest of the current doc version).
- Row count 170 → 169 (−2 deleted, +1 corrected re-store; verified). Re-scan: zero stale current-state ha-fusion claims remain (only the PROTECT-meta scrub record + the new corrected fact reference it).
- Rollback: both original rows in `_archive/lancedb-full-20260609-233532.json`.

## Data-quality counts (tracked, no action)
55 empty-source rows · 53 pre-v2.0 NaN-hash rows · 38 hash-dup rows (mostly prefix-twin class, root-caused + chunker-fixed 2026-06-08; new ingests don't add to it).

## Pointer coverage (orphan ratio)
Current **36.8%** (21/57) vs baseline 25% — +11.8pt, BELOW the 15pt alarm line but drifting. Driver: empty-source seeded facts (Govee/Shield/LG/Sonos cluster) with no MEMORY.md cue. Watch via weekly kb_weekly_audit.sh; if it crosses 40%, run a pointer-backfill pass (add one-line cues for TRUE orphan facts, prune dead ones).

## Cadence (wired 2026-06-09)
- Weekly: dedup + orphan ratio (cron cdd1800159eb, kb_weekly_audit.sh)
- Monthly: full staleness audit (new cron, knowledge-store skill loaded, 1st of month)
