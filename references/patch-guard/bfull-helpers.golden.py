

# ---------------------------------------------------------------------------
# B-full auto-retrieval (per-turn RAG) — cached cold-store engine.
# Loads knowledge.py's hybrid search ONCE (the MiniLM embedding model load is
# ~2.2s; caching it avoids paying that cost on every turn — naive per-turn
# import would be a ~15x latency regression). Returns the module or None;
# None means retrieval is unavailable and the caller must no-op. Retrieval
# must NEVER break a turn, so every failure path here is swallowed.
# ---------------------------------------------------------------------------
_BFULL_ENGINE = None
_BFULL_ENGINE_TRIED = False


def _bfull_engine():
    global _BFULL_ENGINE, _BFULL_ENGINE_TRIED
    if _BFULL_ENGINE_TRIED:
        return _BFULL_ENGINE
    _BFULL_ENGINE_TRIED = True
    try:
        import importlib.util
        _kpath = os.path.expanduser("~/.hermes/scripts/knowledge.py")
        _spec = importlib.util.spec_from_file_location("knowledge_bfull", _kpath)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _BFULL_ENGINE = _mod
        logger.info("[b-full] cold-store retrieval engine loaded")
    except Exception as _e:  # pragma: no cover - defensive
        _BFULL_ENGINE = None
        logger.warning("[b-full] engine load failed, auto-RAG disabled: %s", _e)
    return _BFULL_ENGINE


def _bfull_retrieve(message_text, floor=0.80, top_k=5, max_chars=1000):
    """Return an injection string of cold-store hits >= floor, or '' on any
    failure / no hits. Pure function of the message; never raises."""
    try:
        eng = _bfull_engine()
        if eng is None or not message_text:
            return ""
        import warnings as _warnings
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore", DeprecationWarning)
            hits = eng.search(message_text, top_k=top_k) or []
        lines = []
        for h in hits:
            if not isinstance(h, dict):
                continue
            try:
                score = float(h.get("score", 0) or 0)
            except (TypeError, ValueError):
                continue
            if score >= floor:
                txt = str(h.get("text", "")).strip().replace("\n", " ")[:300]
                if txt:
                    lines.append(f"- [{score:.2f}] {txt}")
        if not lines:
            return ""
        body = "\n".join(lines[:top_k])[:max_chars]
        return ("\n\n[Cold-store auto-retrieval (knowledge.py, score>=0.80) — "
                "treat as a memory cue; verify against live state before "
                "relying on it]:\n" + body)
    except Exception:  # pragma: no cover - retrieval must never break a turn
        return ""
