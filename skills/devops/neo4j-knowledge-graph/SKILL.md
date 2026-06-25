---
name: neo4j-knowledge-graph
description: "Neo4j graph: operate, troubleshoot, Aura pitfalls, MERGE race."
version: 1.0.0
metadata:
  hermes:
    tags: [neo4j, knowledge-graph, aura, pgvector, hybrid-search]
    created_by: agent
load_when:
  - "user asks about Neo4j, knowledge graph, or graph database"
  - "agent needs to troubleshoot Neo4j connection or MERGE errors"
  - "agent needs to backfill knowledge to Neo4j"
---

# Neo4j Knowledge Graph

Production knowledge graph mirroring Supabase facts with pgvector-powered similarity edges.

## Quick Facts

| Detail | Value |
|---|---|
| Instance | Aura Cloud `fce34ad7` (free tier) |
| Database name | `fce34ad7` (NOT `neo4j`) |
| URI | `neo4j+s://fce34ad7.databases.neo4j.io` |
| Driver version | 6.2.0 (dispatcher venv) |
| MCP tool | `mcp-neo4j-cypher` |
| Fact nodes | ~125 |
| RELATED_TO edges | Dynamic (pgvector similarity) |

## Architecture

```
Supabase INSERT → pg_net webhook → hooks.py → MEMORY.md pointer
                                         └──→ Neo4j: MATCH/CREATE (:Fact), pgvector similarity → [:RELATED_TO]

Honcho conclusion → hooks.py → USER.md append
                           └──→ Neo4j: MATCH/CREATE (:Fact), pgvector similarity → [:RELATED_TO]
```

## Schema

| Node | Properties |
|---|---|
| `(:Fact)` | `id, text, tags, priority, source, context_prefix, stored_at` |

| Edge | Meaning |
|---|---|
| `[:RELATED_TO]` | Facts found similar by pgvector (top-3) |
| `[:SUPERSEDES]` | New fact corrects old one (tag: CORRECTION) |

## Environment Variables

All four required in BOTH `config.yaml` (MCP) and `/root/hermes-dispatcher/.env` (dispatcher):

```
NEO4J_URI=neo4j+s://fce34ad7.databases.neo4j.io
NEO4J_USERNAME=fce34ad7
NEO4J_PASSWORD=<from ~/.hermes/.env>
NEO4J_DATABASE=fce34ad7
```

## Critical Pitfalls

### 1. Database name is NOT `neo4j`

Aura free tier names the DB after the instance ID (`fce34ad7`). Every component must specify `NEO4J_DATABASE=fce34ad7`. Defaulting to `neo4j` → `DatabaseNotFound`.

### 2. MERGE + Constraint Race

On a pre-populated database, `MERGE` fails with `ConstraintValidationFailed` because the backing index for the uniqueness constraint hasn't finished building. **Fix:** use `MATCH`-then-`CREATE`/`SET` instead of `MERGE` on nodes.

```python
# WRONG:
s.run("MERGE (f:Fact {id: $id}) SET f.text = $text")

# CORRECT:
result = s.run("MATCH (f:Fact {id: $id}) RETURN f", id=fact_id)
if result.single() is not None:
    s.run("MATCH (f:Fact {id: $id}) SET f.text = $text", ...)
else:
    s.run("CREATE (f:Fact {id: $id}) SET f.text = $text", ...)
```

### 3. pgvector Similarity Parser

`knowledge.py search` returns `[score] [priority] text`, NOT a numbered list. The parser in `hooks.py:_find_similar_via_pgvector()` must match this format. Old parser (expecting `1. text`) returns zero matches silently.

### 4. Python Path in hooks.py

Hardcoded to `/usr/local/lib/hermes-agent/venv/bin/python3`. Changing the venv location breaks pgvector similarity.

### 5. Silent Failure

`_get_neo4j_driver()` returns `None` on failure → `_write_to_neo4j()` is a no-op. Webhook returns 200, zero errors logged at warning level. Always check: `journalctl -u hermes-dashboard | grep neo4j`.

## Verification

After any config/code change:

```bash
# 1. Restart dispatcher
systemctl restart hermes-dashboard

# 2. Verify env vars loaded
cat /proc/$(pgrep -f uvicorn)/environ | tr '\0' '\n' | grep NEO4J

# 3. Trigger test webhook
curl -X POST http://localhost:8787/api/hooks/knowledge \
  -H "Authorization: Bearer <SECRET>" \
  -H "Content-Type: application/json" \
  -d '{"text":"test fact","tags":["test"],"priority":"normal"}'

# 4. Verify in Neo4j
# MCP: MATCH (f:Fact) WHERE f.text CONTAINS "test" RETURN count(f)

# 5. Check edges
# MCP: MATCH ()-[r:RELATED_TO]->() RETURN count(r)

# 6. Check logs for errors
journalctl -u hermes-dashboard --since "1 min ago" | grep "neo4j"
```

## Query Patterns

**Graph traversal:**
```cypher
-- Everything connected to error facts (1-2 hops)
MATCH (f:Fact)-[:RELATED_TO*1..2]-(related)
WHERE "error" IN f.tags RETURN f, related

-- Corrections over time
MATCH (new:Fact)-[:SUPERSEDES]->(old:Fact)
RETURN old.text AS was, new.text AS corrected

-- Facts by source
MATCH (f:Fact {source: "supabase-webhook"})
RETURN f.text, f.tags ORDER BY f.stored_at DESC
```

## Full reference

For complete details (backfill procedure, edge creation code, credential locations), see:
`skill_view('knowledge-store', file_path='references/neo4j-graph-layer.md')`
