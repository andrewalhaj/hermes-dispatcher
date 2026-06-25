---
name: morning-audit
description: "Daily memory audit: hot/warm/cold tiers, retention."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [memory, audit, hygiene, lifecycle]
    created_by: agent
load_when:
  - "user says 'morning audit' or 'memory audit' or 'audit memory'"
  - "memory tier discussion begins"
---

# Morning Memory Audit

Review the three-tier memory system and present candidates for movement. Never make changes without user confirmation.

## Pre-Flight: Honcho Coexistence Check

If Honcho is the active memory provider (`memory.provider: honcho` in config.yaml), the Obsidian tier system (warm/cold) is **frozen legacy** — Honcho handles user modeling automatically via dialectic reasoning. In this mode:

- **Hot store** (`MEMORY.md`): Still active and injected every turn. Audit and compact normally.
- **Warm directory**: Frozen. Skip promotion/demotion candidates from warm. Note its existence but don't suggest moves.
- **Cold directory**: Frozen. Skip entirely.
- **Morning audit report**: Add a header noting "Honcho active — tier system frozen" and skip warm/cold sections.
- **Honcho tools** exist for memory operations: `honcho_search`, `honcho_profile`, `honcho_conclude`. The built-in `memory` tool still operates on hot store only.
- **Cron caveat:** Honcho tools are NOT available in cron context — the plugin intentionally skips initialization (`_cron_skipped = True`, Port #4053). For cron jobs that need Honcho data (e.g., bridging to Obsidian), use the Honcho Python SDK directly. See `references/honcho-cron-bridge.md`.

When Honcho is NOT active, follow the full tier workflow below.

## Step 1 — Read Hot Store

```
read_file /root/.hermes/memories/MEMORY.md
```

Parse entries (delimited by `§`). Note: total chars, count, and each entry's subject + size.

## Step 2 — Check Recent Relevance

For each hot entry, search recent sessions for its key terms:

```
session_search(query="<key terms from entry>", sort="newest", limit=3)
```

Aim for 2-3 searches covering all entries. A hit means the topic appeared in a recent session — strong signal the entry pays rent.

## Step 3 — Read Warm Directory

```
search_files(pattern="*.md", target="files", path="/root/Documents/Obsidian Vault/hermes-memories/warm/")
```

List warm notes. For each, check if it's been manually loaded in recent sessions (search for its filename or topic in sessions).

## Step 4 — Check Cold Directory (if non-empty)

```
search_files(pattern="*.md", target="files", path="/root/Documents/Obsidian Vault/hermes-memories/cold/")
```

Cold entries rarely need attention. Only flag if something in cold was mentioned in a recent session (candidate for warm promotion).

## Step 5 — Apply Rent Test Per Entry

For each hot entry, ask:
> *Will this fact prevent the user from having to repeat or correct themselves in a future session?*

Supported by session_search evidence from Step 2.

## Step 6 — Present Report

Format:

```
☕ Morning Memory Audit — [date]

Hot: X/Y,000 chars (Z%) — N entries

| # | Entry | Size | Rent | Signal |
|---|-------|------|------|--------|
| 1 | ... | ~N | Passes/Fails | Found in M/N recent sessions |

Warm: N notes  |  Cold: N notes

Candidates:
  → Promote (warm→hot): [list or "none"]
  → Demote (hot→warm): [list or "none"]
  → Archive (warm→cold): [list or "none"]
  ✂ Compact: [list or "none"]

[Verdict: No changes needed / Confirm above?]
```

## Rules

1. **Never move without confirmation.** Present candidates, wait for "yes" or "approved."
2. **Err toward keeping hot.** A false demotion costs a future round-trip. A false keep costs ~140 chars.
3. **Demote, don't delete.** Hot→warm preserves the fact. Warm→cold archives it. Only delete truly dead entries (obsolete facts with zero future value).
4. **One change at a time.** Don't batch a promote, a demote, and a compaction into one approval. Present clearly and confirm each category.
5. **Warm notes get individual files.** `warm/topic-name.md` with wikilinks to related notes.
6. **Cold notes get date-stamped context.** `cold/2026-06-01-topic-name.md` for traceability.
7. **Log all moves.** After any change, append to `hermes-memories/audit-log.md`:
   ```
   ## YYYY-MM-DD
   - Promoted: [entry] warm→hot (reason)
   - Demoted: [entry] hot→warm (reason)
   - Archived: [entry] warm→cold (reason)
   ```

## Edge Cases

- **Hot store is empty:** "Hot store is empty. Nothing to audit." Still check warm for promotion candidates.
- **Warm is empty:** Skip warm column in report. Note "no warm notes yet."
- **Cold is empty:** Skip cold column. Normal for new systems.
- **Entry spans multiple topics:** Flag for splitting. "Entry 2 bundles Manifest config + executor profile + cron job. Suggest splitting into 2-3 focused entries."
- **session_search returns noise:** If key terms are too generic to produce meaningful hits, note it: "Session search inconclusive — relying on agent judgment."
