# Session Heartbeat — Incremental Mid-Session Fact Capture

Pushes facts from active (in-progress) Hermes sessions to Supabase knowledge store in near-real-time, without waiting for session end.

## Architecture

```
Cron (every 15 min) → session_heartbeat.py
  → reads state.db for active sessions (ended_at IS NULL, source ≠ subagent/batch)
  → for each session: queries new messages since watermark (messages.id > last_seen)
  → extracts facts from assistant turns (same heuristics as session_capture.py)
  → deduplicates against Supabase (semantic similarity > 0.92 = skip)
  → stores to knowledge.py with tags: [tag, session-heartbeat, <source-platform>]
  → updates watermark file
```

## Watermark

`~/.hermes/references/session-heartbeat-watermark.json`:
```json
{"<session_id>": <last_processed_message_id>, ...}
```

Incremental by design — each run only processes new messages since the last watermark. Message IDs are autoincrement integers (messages.id column).

## Fact Extraction

Reuses `session_capture.py` heuristics:
- **FACTUALLY** — sentences starting with Changed/Fixed/Added/Created/Updated/Deployed/...
- **DECISIONS** — Chose/Selected/Opted/Decided/Went with/Picked
- **CORRECTIONS** — Should have/Instead of/Rather than/Corrected
- **COMMANDS** — inline code blocks with known CLIs (pip, git, curl, docker, hermes, etc.)
- **CONFIG** — `key → value` or `key = value` patterns

Minimum fact length: 25 chars. Cap: 20 facts per run, 50 messages per session.

## Cron Wiring

```bash
hermes cron create \
  --name "Session Heartbeat — real-time fact capture" \
  --schedule "every 15m" \
  --script session_heartbeat.py \
  --no-agent \
  --deliver local
```

`--no-agent` is critical — the script runs directly (no LLM loop). `--deliver local` keeps audit logs on disk.

## Audit

`~/.hermes/references/session-heartbeat-audit.md` — timestamped run summaries:
```
- 2026-06-24T19:52:44+00:00: processed 7 session(s): 0 stored, 10 skipped
```

Silent when no active sessions have new messages (no audit entry, no cron noise).

## Pitfalls

- **state.db must be readable.** If the DB is locked (gateway writing), sqlite3 handles WAL-mode concurrent reads gracefully.
- **Dedup is semantic, not exact.** Two facts with the same meaning but different wording may still be skipped (SIMILARITY_THRESHOLD=0.92).
- **Subagent sessions filtered out.** Only user-facing sessions (source ≠ subagent/batch) are processed.
- **HF_TOKEN warning.** The embedding model loads from HuggingFace on first import of knowledge.py; the unauthenticated rate-limit warning is harmless but noisy. Set `HF_TOKEN` env var to silence it.
