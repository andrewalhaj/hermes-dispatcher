        # -----------------------------------------------------------------
        # B-full auto-retrieval (per-turn RAG). Inject cold-store hits
        # scoring >= 0.80 for the current message into the context prompt
        # BEFORE it is handed to the model. _bfull_retrieve never raises and
        # returns '' on any failure or no-hit, so a retrieval problem can
        # never block or break a turn (no-RAG degrades gracefully to the
        # prior B-lite behavior).
        # -----------------------------------------------------------------
        _bfull_inject = _bfull_retrieve(message_text)
        if _bfull_inject:
            context_prompt += _bfull_inject
