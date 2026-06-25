#!/usr/bin/env python3
"""Auto-retrieval prototype v2 — calls knowledge.py's REAL hybrid search.

v1 bug: passed a raw string to tbl.search() → degenerate, constant 0.50 scores.
Fix: import knowledge.py and use its embed()+search() (vector+BM25 RRF+MMR+graph),
which is the same path that returned 0.88 relevance earlier this session.

Measures per-turn latency and tests the relevance floor (silent when off-topic).
NOT wired into the gateway — offline prototype for the gate decision.
"""
import sys, os, time, importlib.util

HERMES = os.path.expanduser("~/.hermes")
spec = importlib.util.spec_from_file_location("knowledge", f"{HERMES}/scripts/knowledge.py")
K = importlib.util.module_from_spec(spec)
sys.modules["knowledge"] = K
spec.loader.exec_module(K)

RELEVANCE_FLOOR = 0.30   # tune against real scores
TOP_K = 3
MAX_INJECT_CHARS = 600

def retrieve(message):
    t0 = time.time()
    # knowledge.search returns scored results; inspect its shape
    results = K.search(message, top_k=TOP_K)
    elapsed = time.time() - t0
    return results, elapsed

if __name__ == "__main__":
    queries = sys.argv[1:] or [
        "what models does the swarm use",
        "how do I restart the gateway safely",
        "what's the weather like today",      # should stay silent
        "honcho peer resolution pin",
        "tell me a joke",                      # should stay silent
    ]
    print(f"FLOOR={RELEVANCE_FLOOR} TOP_K={TOP_K}\n")
    lat = []
    for q in queries:
        results, elapsed = retrieve(q)
        lat.append(elapsed)
        print(f"Q: {q!r}  ({elapsed*1000:.0f}ms)")
        # print raw result shape once so we see the score field
        for r in (results or [])[:TOP_K]:
            if isinstance(r, dict):
                score = r.get("score", r.get("_relevance_score", r.get("rrf", "?")))
                txt = str(r.get("text", ""))[:110].replace("\n", " ")
            else:
                score, txt = "?", str(r)[:110]
            print(f"     [{score}] {txt}")
        print()
    print(f"=== latency avg={sum(lat)/len(lat)*1000:.0f}ms max={max(lat)*1000:.0f}ms (first incl. model load) ===")
