# Delegation Debug Handoff — 2026-06-17 (CLOSED 2026-06-18)

**Status: RESOLVED** — `delegate_task` routes correctly to `qwen2.5-32b-64k` on Mac Studio.

---

## Resolution (2026-06-18, session 3)

The handoff's hypothesis about `_check_ollama_runtime_context` was a red herring.

**Actual root cause:** `delegation.model` was pointing at `qwen2.5-coder-14b-32k`. Coder
variants return tool-calls as plain text (not structured `tool_calls` JSON) through Ollama's
OpenAI endpoint → the child agent can't parse the response → falls to DeepSeek. All five
context/key gates were already satisfied. This was documented in the definitive findings doc
but the config drifted after that doc was written.

**Fix:** `delegation.model: qwen2.5-32b-64k` (restored to the confirmed-working value).

**Verified:** `delegate_task` returned `model: qwen2.5-32b-64k`, 37s, `exit_reason: completed`.

---

## Authoritative reference

See `references/studio-delegation-findings-2026-06-18.md` — the full failure chain is there.
If delegation breaks again, read that doc first. Walk all five gates (declared context_length,
live `_ollama_num_ctx`, child_timeout_seconds, api_key_env, model name exists + tool-calls
correctly) before touching config.

---

## Live config (verified working)

```yaml
delegation:
  model: qwen2.5-32b-64k
  provider: custom:mac-studio
  base_url: http://100.93.2.43:11434/v1
  child_timeout_seconds: 900
  max_concurrent_children: 12

model:
  ollama_num_ctx: 65536   # gate #2 override — still needed

custom_providers:
  mac-studio:
    base_url: http://100.93.2.43:11434/v1
    models:
      qwen2.5-32b-64k:
        context_length: 65536   # gate #1
      qwen2.5-coder-14b-32k:
        context_length: 65536   # declared but NON-VIABLE (text tool-calls)
```

---

## Models on Studio disk (as of 2026-06-18)

| Model | Size | Delegation-viable? |
|---|---|---|
| qwen2.5-32b-64k | 19.9 GB | ✅ YES (confirmed working) |
| qwen2.5:72b | 47.4 GB | ✅ YES (too slow for delegation, fits solo) |
| qwen2.5-coder-14b-32k | 9.0 GB | ❌ NO (text tool-calls) |
| qwen2.5-coder:14b | 9.0 GB | ❌ NO (text tool-calls) |

`qwen2.5-128k` is declared in custom_providers but NOT on disk — would 404.
~37 GB reclaimable from the two coder orphans if you want to clean up.

---

## Open question from prior session

P=1 vs P=2 for the Studio Ollama instance was deferred. P=1 is optimal for
sequential delegation (prefix cache reuse); P=2 adds throughput for concurrent
fan-out but defeats caching. Currently unset — check with
`ssh localadmin@100.93.2.43 '...'` if needed.
