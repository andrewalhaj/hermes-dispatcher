# Supabase pg_net → Hermes Webhook Pattern

End-to-end pattern: Supabase table INSERT → pg_net trigger → Cloudflare Tunnel → Hermes FastAPI webhook receiver.

## Architecture

```
knowledge.py store() → INSERT public.knowledge
  → trigger knowledge_insert_webhook
    → net.http_post(url, body, headers)
      → https://hermes.andrewskingdom.com/api/hooks/knowledge
        → routes/hooks.py → MEMORY.md pointer append
```

## Supabase Migration: Trigger Function

The CORRECT pg_net function signature (Supabase docs, v3):

```sql
CREATE OR REPLACE FUNCTION public.on_knowledge_insert()
RETURNS TRIGGER AS $$
DECLARE
  _url    constant text := 'https://hermes.andrewskingdom.com/api/hooks/knowledge';
  _secret constant text := '<64-char hex>';
  _payload jsonb;
  _headers jsonb;
BEGIN
  _payload := jsonb_build_object(
    'id',       NEW.id,
    'text',     left(NEW.text, 200),
    'tags',     to_jsonb(NEW.tags),
    'source',   NEW.source,
    'priority', NEW.priority
  );

  _headers := jsonb_build_object(
    'Content-Type', 'application/json',
    'Authorization', 'Bearer ' || _secret
  );

  PERFORM net.http_post(
    url     := _url,
    body    := _payload,
    headers := _headers
  );

  RETURN NEW;
EXCEPTION WHEN OTHERS THEN
  RAISE LOG 'webhook failed (row %): %', NEW.id, SQLERRM;
  RETURN NEW;  -- never block the INSERT
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS knowledge_insert_webhook ON public.knowledge;
CREATE TRIGGER knowledge_insert_webhook
  AFTER INSERT ON public.knowledge
  FOR EACH ROW EXECUTE FUNCTION public.on_knowledge_insert();
```

## Pitfalls (DISCOVERED HARD WAY)

1. **WRONG SCHEMA**: Functions live in `net` schema, NOT `extensions`. Use `net.http_post()`, not `extensions.http_post()`.
2. **WRONG HEADERS TYPE**: `headers` parameter is `jsonb`, NOT `ARRAY[extensions.http_header(...)]`. The array + http_header pattern does not exist.
3. **WRONG SIGNATURE**: The old `extensions.http_post(url, body::text, headers ARRAY)` signature fails. Correct is `net.http_post(url text, body jsonb, params jsonb DEFAULT, headers jsonb DEFAULT, timeout_milliseconds int DEFAULT)`.
4. **CLOUDFLARE BOT FIGHT MODE**: pg_net requests originate from Supabase datacenter IPs. Cloudflare Bot Fight Mode blocks them with error 1010. FIX: WAF custom rule to skip Bot Fight Mode for the webhook URL path.
5. **AUTH EXEMPTION**: The webhook endpoint must be in the FastAPI `_AUTH_EXEMPT` set — pg_net can't send session cookies.
6. **RLS**: Enable RLS on the source table with service_role bypass. pg_net triggers are SECURITY DEFINER and run as the table owner.
7. **SECRET MISMATCH**: The `.env` file and the trigger function must have the SAME secret. Generate once, embed in both. The redaction system (write_file/terminal) truncates hex values — generate secrets inside execute_code to keep them intact.

## Hermes Route

See `routes/hooks.py` in hermes-dispatcher. Pattern:
- `POST /api/hooks/knowledge` 
- Bearer token auth via `WEBHOOK_SECRET` env var
- Deduplication by term prefix
- `[auto]` label on generated MEMORY.md pointers

## WAF Skip Rule

Cloudflare Dashboard → Security → WAF → Custom Rules:
- When: `URI Path` equals `/api/hooks/knowledge`
- Action: Skip → Bot Fight Mode
