# Neo4j Graph Layer — Knowledge Mirror

> **Canonical reference:** `productivity/knowledge-store/references/neo4j-graph-layer.md` — contains the full production setup, MERGE constraint race fix, pgvector similarity parser, backfill procedure, Aura specifics, and all pitfalls. This file is a routing pointer; consult the canonical version for details.

## Quick Facts

- **Instance:** Aura Cloud `fce34ad7` (free tier)
- **Database:** `fce34ad7` (NOT `neo4j` — free tier names DB after instance ID)
- **Username:** `fce34ad7` (NOT `neo4j` — free tier uses instance ID as user)
- **Connection:** `neo4j+s://fce34ad7.databases.neo4j.io`
- **Driver in dispatcher:** `neo4j` v6.2.0 in `/root/hermes-dispatcher/.venv/`
- **Handler:** `/root/hermes-dispatcher/routes/hooks.py` lines 40–280
- **MCP server:** `config.yaml` → `mcp-neo4j-cypher` (uvx)

## Pipeline

```
Supabase INSERT ──→ pg_net webhook ──→ hooks.py ──→ MEMORY.md pointer
                                               └──→ Neo4j: create/update (:Fact), pgvector similarity → RELATED_TO edges

Honcho conclusion ──→ hooks.py ──→ USER.md append
                                └──→ Neo4j: create/update (:Fact), pgvector similarity → RELATED_TO edges
```

## Key Pitfalls (from canonical reference)

Refer to the canonical reference for full details. Summary:

1. **Database name ≠ `neo4j`** on Aura free tier — must set `NEO4J_DATABASE=fce34ad7` everywhere
2. **MERGE + constraint race** on pre-populated DB — use MATCH+CREATE/SET instead of MERGE-on-nodes
3. **knowledge.py parser** expects `[score] [priority] text` format, not numbered list
4. **Dispatcher env** comes from `/root/hermes-dispatcher/.env` via systemd `EnvironmentFile`, NOT from `~/.hermes/.env`
5. **SILENT FAILURE:** `_get_neo4j_driver()` returns None on init failure → all writes are no-ops → webhook still returns 200
6. **MCP config changes** need `hermes gateway restart` to take effect
7. **Python path** in hooks.py is hardcoded to `/usr/local/lib/hermes-agent/venv/bin/python3`
