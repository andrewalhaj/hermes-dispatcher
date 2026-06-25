# B-full implementation recipe (scoped against live run.py, 2026-06-09)

The crossover decision lives in SKILL.md; this is the concrete WIRING if/when B-full
is greenlit. Scoped against the real `gateway/run.py` (20,031 lines) this session — the
architecture doc (`knowledge-store/references/auto-retrieval-architecture.md`) describes
B-full abstractly; this is the implementable version with the gotchas found in the code.

## Status: APPLIED + LIVE 2026-06-09 (Andrew directed the switch). This is the as-built record.

> Was "recipe only / gated" until 2026-06-09, when Andrew directed B-lite → B-full and it shipped. The wiring below is what actually landed in `gateway/run.py` (PID rotated at deploy; backup `run.py.bak-20260609-062713-prebfull`). Two refinements vs the original recipe draft: (a) the cache uses a `_BFULL_ENGINE_TRIED` flag so a FAILED engine load doesn't retry every turn (the bare `_BFULL_K is None` version would re-attempt a broken import on every message); (b) the retrieval logic is factored into a named `_bfull_retrieve(message_text)` helper rather than an inline try/except, so patch_guard can re-insert it as a clean block. See SKILL.md "B-full deployment (LIVE 2026-06-09)" for the maintained reference.

## The real injection seam (verified, not the skill's approximate ~9459)

- `context_prompt` is assembled at `build_session_context_prompt(...)` (~line 8994).
- It accumulates additions (first-msg onboarding ~9419, Discord voice-channel ~9459).
- `message_text` is finalized at ~9473 (`_prepare_inbound_message_text`); guard `if message_text is None: return` at ~9478.
- It is then passed to `_run_agent(context_prompt=context_prompt, ...)` at ~9504 and handed to the model as a **system message** at ~9784 (`api_messages.append({"role":"system","content":context_prompt})`).
- **Inject point: right after the `message_text is None` guard (~9479), before the `_run_agent` call (~9502).** At that point `message_text` exists and `context_prompt` is still mutable.

## The patch block (fail-safe, never breaks a turn)

```python
# B-full auto-retrieval (per-turn RAG) — inject cold-store hits >=0.80.
# Fail-safe: any error swallowed so retrieval can NEVER break a turn.
try:
    if message_text:
        _K = _bfull_engine()                      # cached import — see gotcha below
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            _hits = _K.search(message_text, top_k=3) or []
        _lines = [f"- [{h['score']:.2f}] {str(h.get('text','')).strip()[:300]}"
                  for h in _hits
                  if isinstance(h, dict) and h.get("score", 0) >= 0.80]
        if _lines:
            context_prompt += ("\n\n[Cold-store auto-retrieval (>=0.80) — "
                "verify against live state]:\n" + "\n".join(_lines[:3])[:600])
except Exception:
    pass
```

## THE GOTCHA the spec glosses: embedding-model caching (latency 15× off if missed)

The architecture doc quotes "~150ms/turn" — that assumes the MiniLM embedding model is
loaded ONCE. The prototype (`auto_retrieve_proto.py`) `exec_module`s knowledge.py fresh,
which reloads the model on every call (~2.2s). Naively wiring that into the seam = **~2.2s
tax on EVERY message**, infra-topical or not — a latency regression, not the advertised cost.

Fix: a module-level cached importer, loaded once on first use:

```python
_BFULL_K = None
def _bfull_engine():
    global _BFULL_K
    if _BFULL_K is None:
        import importlib.util, os
        p = os.path.expanduser("~/.hermes/scripts/knowledge.py")  # DEFAULT profile path, explicit
        spec = importlib.util.spec_from_file_location("knowledge_bfull", p)
        _BFULL_K = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_BFULL_K)
    return _BFULL_K
```

Confirm the cache holds across turns on a long-lived gateway (it does — the module object
persists in the gateway process). First message after a restart pays the ~2.2s load once.

## Protection (DONE — registered, not pending)

Core patches are stripped by `hermes update`. **As shipped:** registered as `_heal_bfull()` (run-check #5) in `scripts/patch_guard.py` — surgical re-apply (re-inserts the two blocks at their anchors), NOT a whole-file restore, because run.py is a 20k-line upstream file `hermes update` legitimately rewrites (same treatment as the Honcho drift patch). Golden text blocks: `~/.hermes/references/patch-guard/bfull-helpers.golden.py` + `bfull-injection.golden.py`. The 05:00 "Patch Guard Self-Heal" cron already calls patch_guard.py, so it's covered automatically. Proven: strip-then-reheal on a copy restores a compiling file; patch_guard runs silent when the marker is present (no false heal).

## Apply sequence (all gated — present diff first, backup, then execute)

1. `.bak` the live `run.py` (`cp .../gateway/run.py .../gateway/run.py.bak-<ts>-prebfull`).
2. Insert the cached importer (module scope) + the inject block (after ~9479). Add `import warnings` if not already imported at module top.
3. Restart gateway DETACHED: `systemd-run --user --scope --collect bash -c 'XDG_RUNTIME_DIR=/run/user/0 systemctl --user restart hermes-gateway.service'`. The ~60s "timeout" is the drain, not a failure.
4. Register golden artifact + self-heal cron entry.
5. VERIFY a turn actually gets injection (send an infra-topical message, confirm the cold-store block appears) — and confirm a non-topical message does NOT pay the 2.2s (cache warm).

## Why this likely does NOT fix the symptom that prompts the ask

The recurring trigger for "switch to B-full" is "a stored fact didn't surface." But B-full
injects the SAME embeddings at the SAME ≥0.80 floor — the orphan-below-floor case (fact at
0.74, see SKILL.md) is injected by neither B-lite nor B-full. The actual fix for sub-floor
facts is **Stage 3 (cross-encoder reranker)**, which lifts true hits above the floor, OR a
hot pointer. State this honestly when B-full is requested for that reason — it's buildable
and correct as unconditional RAG, but it's not the remedy for low-scoring facts.

## Rollback

Restore the `.bak` run.py + remove the golden artifact + restart. One-file, fully reversible.
