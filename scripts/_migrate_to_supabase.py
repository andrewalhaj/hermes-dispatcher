#!/usr/bin/env python3
"""One-shot migration: load /tmp/migration_data.json → Supabase knowledge table.

Idempotent: uses upsert on id so re-runs are safe.
Run: python3 ~/.hermes/scripts/_migrate_to_supabase.py
"""
import json
import os
import sys
from datetime import datetime, timezone

# -- Load knowledge.py helpers so we share env-loading and client init ----
import importlib.util
_KB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge.py')
spec = importlib.util.spec_from_file_location('knowledge', _KB_PATH)
kb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kb)

MIGRATION_FILE = '/tmp/migration_data.json'
TABLE_NAME = 'knowledge'


def epoch_to_iso(epoch):
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat()


def main():
    if not os.path.exists(MIGRATION_FILE):
        print(f"ERROR: {MIGRATION_FILE} not found", file=sys.stderr)
        sys.exit(1)

    with open(MIGRATION_FILE) as f:
        raw_rows = json.load(f)

    print(f"Loaded {len(raw_rows)} rows from {MIGRATION_FILE}")

    client = kb.get_db()

    rows_to_upsert = []
    for r in raw_rows:
        # stored_at: epoch float → ISO timestamptz string
        stored_at_raw = r.get('stored_at')
        if stored_at_raw is not None:
            stored_at_iso = epoch_to_iso(stored_at_raw)
        else:
            stored_at_iso = datetime.now(tz=timezone.utc).isoformat()

        # tags: JSON string → Python list (Supabase stores as jsonb)
        tags_raw = r.get('tags', '[]')
        if isinstance(tags_raw, str):
            try:
                tags = json.loads(tags_raw)
            except Exception:
                tags = []
        elif isinstance(tags_raw, list):
            tags = tags_raw
        else:
            tags = []

        # vector: already a Python list (pass as-is; pgvector accepts JSON array)
        vector = r.get('vector')
        if not isinstance(vector, list):
            print(f"  SKIP {r['id']}: vector missing or wrong type", file=sys.stderr)
            continue

        rows_to_upsert.append({
            'id': r['id'],
            'text': r.get('text', ''),
            'vector': vector,
            'tags': tags,
            'priority': r.get('priority', 'normal'),
            'source': r.get('source', '') or '',
            'stored_at': stored_at_iso,
            'context_prefix': r.get('context_prefix', '') or '',
            'body_hash': r.get('body_hash', '') or '',
        })

    if not rows_to_upsert:
        print("No rows to insert.", file=sys.stderr)
        sys.exit(1)

    print(f"Upserting {len(rows_to_upsert)} rows into Supabase table '{TABLE_NAME}'...")
    resp = client.table(TABLE_NAME).upsert(rows_to_upsert, on_conflict='id').execute()

    if resp.data is not None:
        inserted = len(resp.data)
        print(f"Upserted {inserted} rows successfully.")
    else:
        print(f"Upsert completed (no data returned by API — check Supabase dashboard).")

    # Verify row count
    count_resp = client.table(TABLE_NAME).select('id', count='exact').execute()
    total = count_resp.count if count_resp.count is not None else len(count_resp.data or [])
    print(f"Total rows in Supabase '{TABLE_NAME}': {total}")


if __name__ == '__main__':
    main()
