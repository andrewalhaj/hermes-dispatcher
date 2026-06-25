# Neo4j Graph Layer — Production Reference

> **Instance:** Aura Cloud `fce34ad7` (free tier). Database name = `fce34ad7` (same as instance ID on free tier, NOT `neo4j`).
> **Canonical live config:** `/root/hermes-dispatcher/routes/hooks.py` lines 40–280 (driver + writer + pgvector similarity + edges).
> **MCP access:** `config.yaml` → `mcp_servers.neo4j` → `mcp-neo4j-cypher` over `neo4j+s://fce34ad7.databases.neo4j.io`.

## Architecture

```
Supabase INSERT ──→ pg_net webhook ──→ hooks.py ──→ MEMORY.md pointer
                                               └──→ Neo4j: MATCH/CREATE (:Fact), find related, link

Honcho conclusion ──→ hooks.py ──→ USER.md append
                                └──→ Neo4j: MATCH/CREATE (:Fact), find related, link
```

## Schema

| Node | Properties |
|---|---|
| `(:Fact)` | `id, text, tags, priority, source, context_prefix, stored_at` |
| `(:Session)` | `session_id, timestamp` (reserved, not yet populated) |

| Edge | Meaning |
|---|---|
| `[:RELATED_TO]` | Facts found similar by pgvector (top-3, cosine > threshold) |
| `[:SUPERSEDES]` | New fact corrects an old one (when tagged CORRECTION) |

## Credentials & Environment

**All four env vars required in BOTH locations:**

### 1. Dispatcher `.env` (`/root/hermes-dispatcher/.env`)
```
NEO4J_URI=neo4j+s://fce34ad7.databases.neo4j.io
NEO4J_USERNAME=fce34ad7
NEO4J_PASSWORD=<from ~/.hermes/.env>
NEO4J_DATABASE=fce34ad7
```

The dispatcher systemd unit (`hermes-dashboard.service`) has `EnvironmentFile=/root/hermes-dispatcher/.env` via `dispatcher-override.conf`. Without this file, the driver silently fails to initialize — no errors, just never writes.

### 2. Hermes `config.yaml` (MCP server)
```yaml
neo4j:
  env:
    NEO4J_DATABASE: fce34ad7
    NEO4J_URI: neo4j+s://fce34ad7.databases.neo4j.io
    NEO4J_USERNAME: fce34ad7
    NEO4J_PASSWORD: ${NEO4J_PASSWORD}
```

After editing `config.yaml`, MCP needs `hermes gateway restart` to pick up the change.

## Constraints

```cypher
CREATE CONSTRAINT fact_id IF NOT EXISTS FOR (f:Fact) REQUIRE f.id IS UNIQUE
CREATE INDEX fact_tags IF NOT EXISTS FOR (f:Fact) ON f.tags
```

## Critical Pitfall: MERGE + Constraint Race on Pre-Populated DB

**The problem:** When `_init_neo4j()` creates the `fact_id` uniqueness constraint on a database that ALREADY contains `(:Fact)` nodes (e.g., after a backfill), the constraint's backing index may not finish building immediately. `MERGE` uses the index to look up existing nodes — if the index isn't ready, `MERGE`'s MATCH phase finds nothing, tries to CREATE, and hits the constraint violation: `Node(N) already exists with label Fact and property id = 'X'`.

**The fix:** Replace ALL `MERGE`-on-nodes with explicit `MATCH`-then-`CREATE`/`SET`. In `hooks.py`:

```python
# INSTEAD OF:
s.run("MERGE (f:Fact {id: $id}) SET f.text = $text, ...")

# USE:
result = s.run("MATCH (f:Fact {id: $id}) RETURN f", id=fact_id)
if result.single() is not None:
    s.run("MATCH (f:Fact {id: $id}) SET f.text = $text, ...")
else:
    s.run("CREATE (f:Fact {id: $id}) SET f.text = $text, ...")
```

Same pattern applies to `[:RELATED_TO]` and `[:SUPERSEDES]` edge creation — MATCH the nodes first, then MERGE the edge only (edges don't have uniqueness constraints so MERGE is safe for those).

## pgvector Similarity: Knowledge.py Parser

`_find_similar_via_pgvector()` shells out to `knowledge.py search` via the CORRECT Python path:

```python
subprocess.run([
    "/usr/local/lib/hermes-agent/venv/bin/python3",
    "/root/.hermes/scripts/knowledge.py", "search", clean, "--limit", "3"
], capture_output=True, text=True, timeout=8,
   env={**os.environ, "HERMES_HOME": str(HERMES_HOME)})
```

**Parser must match the actual output format:**

knowledge.py returns results as:
```
[0.4742] [high] the actual fact text here
  tags: [...]  id: xxx
```

The parser extracts text from the `[score] [priority]` line:
```python
for line in result.stdout.splitlines():
    line = line.strip()
    if line.startswith("[") and "] [" in line:
        rest = line.split("] [", 2)[-1]
        if "] " in rest:
            text_part = rest.split("] ", 1)[1].strip()
            if text_part:
                matches.append(text_part)
```

**Common failure:** The old parser expected `1. text here` (numbered list format). That parser returns empty for every query — zero matches, zero edges, silent degradation. The `[score] [priority]` format is the correct one.

## Backfill Procedure

To populate Neo4j from existing Supabase rows:

1. Use the `SUPABASE_SERVICE_KEY` (bypasses RLS, which blocks anon key reads on `public.knowledge`).
2. POST each row to the local webhook endpoint `http://localhost:8787/api/hooks/knowledge` with `Authorization: Bearer <WEBHOOK_SECRET>`.
3. The webhook handler handles deduplication (SHA-256[:16] hash of text) and pgvector similarity edge creation.

**Why webhook and not direct Neo4j driver:** The webhook exercises the same code path as production ingestion — constraint setup, MEMORY.md dedup, pgvector similarity — so the backfill validates the pipeline. Direct driver writes skip validation.

**171 rows backfilled → 112 unique in Neo4j** (59 deduped by hash collision — mostly duplicate/empty test entries).

## Aura Free Tier Specifics

| Fact | Value |
|---|---|
| Instance ID | `fce34ad7` |
| Connection URI | `neo4j+s://fce34ad7.databases.neo4j.io` |
| Database name | `fce34ad7` (same as instance ID) |
| Username | `fce34ad7` (same as instance ID) |
| Password | `${NEO4J_PASSWORD}` from `~/.hermes/.env` |

**The default database is NEVER named `neo4j` on Aura free tier.** Every connection that doesn't specify a database name gets `DatabaseNotFound`. Must pass `NEO4J_DATABASE=fce34ad7` everywhere:
- `drv.session(database=NEO4J_DATABASE)` in hooks.py
- `NEO4J_DATABASE: fce34ad7` in config.yaml MCP env
- `NEO4J_DATABASE=fce34ad7` in dispatcher `.env`

## Query Patterns

### Neo4j (Graph)

```cypher
-- Facts related to a topic (1-2 hops)
MATCH (f:Fact)-[:RELATED_TO*1..2]-(related)
WHERE "error" IN f.tags
RETURN f, related

-- Corrections made over time
MATCH (new:Fact)-[:SUPERSEDES]->(old:Fact)
RETURN old.text AS was, new.text AS corrected

-- Facts from a specific source
MATCH (f:Fact {source: "honcho-webhook"})
RETURN f.text, f.tags, f.priority
ORDER BY f.stored_at DESC

-- Graph statistics
MATCH (n) RETURN labels(n) AS labels, count(*) AS cnt
MATCH ()-[r]->() RETURN type(r) AS edge_type, count(*) AS cnt
```

### Supabase (Hybrid — pgvector + Full-Text)

```sql
-- Keyword search (FTS)
SELECT id, LEFT(text, 60), ts_rank(tsv, query) AS rank
FROM public.knowledge, to_tsquery('english', 'neo4j & pipeline') AS query
WHERE tsv @@ query
ORDER BY rank DESC LIMIT 10;

-- Combined: keyword + semantic (application-layer merge via knowledge.py v3.0)
-- knowledge.py search already does adaptive BM25+vector fusion with MMR diversity
python3 ~/.hermes/scripts/knowledge.py search "neo4j pipeline configuration"
```

The `tsv` column is auto-populated via trigger on INSERT/UPDATE. GIN index enables sub-millisecond FTS.

## Verification

After any config/hooks.py change:

1. **Restart dispatcher:** `kill -HUP` or `systemctl restart hermes-dashboard`
2. **Verify env:** `cat /proc/$(pgrep -f uvicorn)/environ | tr '\0' '\n' | grep NEO4J`
3. **Trigger test webhook** with unique text:
   ```python
   POST http://localhost:8787/api/hooks/knowledge
   Authorization: Bearer <WEBHOOK_SECRET>
   {"text": "test fact at timestamp <ts>", "tags": ["test"], "priority": "normal"}
   ```
4. **Check Neo4j:** `MATCH (f:Fact) WHERE f.text CONTAINS "test fact" RETURN f`
5. **Check edges:** `MATCH ()-[r:RELATED_TO]->() RETURN count(r)` — should be > 0 after a non-duplicate write
6. **Check logs:** `journalctl -u hermes-dashboard --since "1 min ago" | grep neo4j` — no `write failed` or `ConstraintValidationFailed` lines

## Pitfalls

- **Database name ≠ `neo4j` on Aura free tier.** The default IS the instance ID. Every component must specify it.
- **MERGE + constraint race.** On a pre-populated DB, use MATCH+CREATE/SET instead of MERGE-on-nodes.
- **knowledge.py parser format.** Output is `[score] [priority] text`, not a numbered list.
- **Python path in hooks.py.** Hardcodes `/usr/local/lib/hermes-agent/venv/bin/python3` — changing the venv location breaks pgvector similarity silently.
- **config.yaml MCP changes need gateway restart.** `hermes gateway restart` required; can't be done from within the gateway.
- **Dispatcher `.env` is separate from `~/.hermes/.env`.** The systemd unit reads from `/root/hermes-dispatcher/.env`. Add NEO4J vars there too.
- **`neo4j` driver must be installed** in the dispatcher venv (`/root/hermes-dispatcher/.venv/`). v6.2.0 confirmed working.
- **SILENT FAILURE TRAP.** `_get_neo4j_driver()` returns `None` on init failure → `_write_to_neo4j()` is a no-op. Webhook returns 200, zero errors, zero facts. Always check `journalctl | grep neo4j` after changes.
