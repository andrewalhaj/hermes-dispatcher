#!/usr/bin/env python3
"""
offload_probe.py — mechanical "probe-then-trim" memory offload advisor
=======================================================================

Makes the knowledge-store offload protocol mechanical: given a hot-memory
fact, probe Supabase knowledge store with realistic query phrasings and return a verdict.

  TRIM-SAFE   → every query finds the fact ≥0.80; can delete from MEMORY.md
  POINTER     → at least one query finds it ≥0.80; keep a one-line cue
  KEEP-HOT    → no query returns ≥0.80; must stay in hot memory

USAGE
-----
  # Probe a single fact with explicit queries
  offload_probe.py probe --fact "hil-1 is 32GB/8vCPU" --queries "hil-1 specs" "server RAM" "host specs"

  # Probe a fact with auto-generated queries (no LLM)
  offload_probe.py probe --fact "hil-1 is 32GB/8vCPU"

  # Scan all non-pointer MEMORY.md entries
  offload_probe.py scan

  # JSON output
  offload_probe.py scan --json

READ-ONLY: never modifies MEMORY.md or the Supabase knowledge store.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────

HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
MEMORY_PATH = os.path.join(HERMES_HOME, "memories", "MEMORY.md")
KNOWLEDGE_PY = os.path.join(HERMES_HOME, "scripts", "knowledge.py")
FLOOR = 0.80           # auto-RAG injection floor
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from",
    "has", "he", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "this", "to", "was", "were", "will", "with", "via", "so", "if", "not",
    "no", "we", "use", "used", "can", "per", "all", "any", "when", "then",
    "than", "they", "been", "have", "after", "also", "into", "about", "now",
}

# ── Load knowledge.py as module ───────────────────────────────────────────────

def _load_knowledge():
    try:
        spec = importlib.util.spec_from_file_location("knowledge", KNOWLEDGE_PY)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:
        print(f"ERROR: cannot load {KNOWLEDGE_PY}: {exc}", file=sys.stderr)
        sys.exit(2)


# ── Query auto-generation (no LLM) ───────────────────────────────────────────

_IDENTIFIER_RE = re.compile(r"[A-Z_]{2,}|[a-zA-Z0-9][\w.-]*:[\w./-]+|localhost:\d+|\d{2,5}|[a-z0-9-]+\.[a-z]{2,4}")
_PUNCT = re.compile(r"[^\w\s.:-]")


def _tokens(text: str) -> list[str]:
    cleaned = _PUNCT.sub(" ", text.lower())
    return [t for t in cleaned.split() if t and t not in STOPWORDS and len(t) > 1]


def auto_queries(fact: str) -> list[str]:
    """Generate 3 deterministic probe queries from a fact string."""
    words = _tokens(fact)

    # (a) 6 highest-information tokens (by length as a cheap proxy)
    tfidf_proxy = sorted(set(words), key=lambda w: (-len(w), w))[:6]
    q_a = " ".join(tfidf_proxy) if tfidf_proxy else fact[:60]

    # (b) most distinctive content tokens — longest tokens are the best
    #     search terms regardless of fact type (technical: 32GB, hil-1;
    #     behavioral: upgradeable, blocked, dotfile). Sorted by length,
    #     deduplicated, capped at 5 tokens.
    distinct = sorted(set(words), key=lambda w: (-len(w), w))[:5]
    q_b = " ".join(distinct) if distinct else q_a

    # (c) first 8 content words verbatim
    content_words = [w for w in fact.split() if w.lower() not in STOPWORDS][:8]
    q_c = " ".join(content_words) if content_words else fact[:60]

    # Deduplicate while preserving order
    seen, queries = set(), []
    for q in [q_a, q_b, q_c]:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            queries.append(q)
    while len(queries) < 3:
        queries.append(queries[-1])
    return queries[:3]


# ── Score + match logic ───────────────────────────────────────────────────────

def _best_score_and_match(results: list[dict], fact: str) -> tuple[float, bool]:
    """Return (best_score, fact_found_in_top3)."""
    if not results:
        return 0.0, False

    best_score = max(r.get("score", r.get("_relevance_score", 0.0)) for r in results)
    fact_lower = fact.lower()
    fact_toks = set(_tokens(fact))

    found = False
    for r in results[:3]:
        hit_text = (r.get("text") or "").lower()
        # Fuzzy: token overlap ≥ 0.6
        hit_toks = set(_tokens(hit_text))
        if fact_toks and len(fact_toks & hit_toks) / len(fact_toks) >= 0.6:
            found = True
            break
        # Or: a distinctive 12-char substring of the fact is in the hit
        fact_stripped = _PUNCT.sub("", fact_lower).replace(" ", "")
        hit_stripped = _PUNCT.sub("", hit_text).replace(" ", "")
        for i in range(0, len(fact_stripped) - 11, 4):
            chunk = fact_stripped[i:i+12]
            if chunk and chunk in hit_stripped:
                found = True
                break
        if found:
            break

    return best_score, found


def probe_fact(knowledge_mod, fact: str, queries: list[str]) -> dict:
    """Probe a fact against the store. Returns a structured result dict."""
    results_per_query = []
    for q in queries:
        try:
            hits = knowledge_mod.search(q, top_k=5, use_graph=False)
        except Exception as exc:
            hits = []
        score, found = _best_score_and_match(hits, fact)
        results_per_query.append({
            "query": q,
            "best_score": round(score, 3),
            "fact_found": found,
            "above_floor": score >= FLOOR,
            "query_passed": (score >= FLOOR) or (found and score >= 0.60),
        })

    # A query "passes" if it either (a) scores ≥FLOOR, or (b) actually found the
    # fact text (token overlap / substring match) with a reasonable score ≥0.60.
    # Without (b), behavioral facts never clear 0.80 — their embeddings inherently
    # plateau lower than technical facts'.  fact_found is the stronger signal;
    # cosine score is the guard.  Together they answer "can I retrieve this?"
    # instead of "did the vector math happen to be >0.80 today."
    def _query_passed(r: dict) -> bool:
        if r["above_floor"]:
            return True
        return r["fact_found"] and r["best_score"] >= 0.60

    all_passed = all(_query_passed(r) for r in results_per_query)
    any_passed = any(_query_passed(r) for r in results_per_query)

    if all_passed:
        verdict = "TRIM-SAFE"
    elif any_passed:
        verdict = "POINTER"
    else:
        verdict = "KEEP-HOT"

    return {
        "fact": fact,
        "verdict": verdict,
        "queries": results_per_query,
    }


# ── MEMORY.md parser ──────────────────────────────────────────────────────────

def _read_memory_entries() -> list[str]:
    try:
        text = Path(MEMORY_PATH).read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"ERROR: {MEMORY_PATH} not found", file=sys.stderr)
        sys.exit(2)

    # Strip section header (everything before the first §)
    entries = []
    raw = text.split("\n§\n")
    for chunk in raw:
        entry = chunk.strip()
        # Skip the header block (contains ══ markers)
        if "══" in entry and "MEMORY" in entry:
            # May still have content after the header line
            lines = entry.split("\n")
            content_lines = [l for l in lines if not l.startswith("══") and "MEMORY" not in l and "USER PROFILE" not in l]
            entry = "\n".join(content_lines).strip()
        if entry:
            entries.append(entry)
    return [e for e in entries if e]


def _is_pointer_entry(entry: str) -> bool:
    """Entries that already reference knowledge.py search are pointers — skip."""
    return "knowledge.py search" in entry or "knowledge.py" in entry


# ── Scan mode ─────────────────────────────────────────────────────────────────

def cmd_scan(knowledge_mod, as_json: bool):
    entries = _read_memory_entries()
    to_probe = [(i, e) for i, e in enumerate(entries) if not _is_pointer_entry(e)]
    pointer_entries = [(i, e) for i, e in enumerate(entries) if _is_pointer_entry(e)]

    trim_safe, pointer_results, keep_hot = [], [], []

    total = len(to_probe)
    for idx, (i, entry) in enumerate(to_probe, 1):
        if not as_json:
            print(f"  probing {idx}/{total}...", end="\r", flush=True)
        queries = auto_queries(entry)
        result = probe_fact(knowledge_mod, entry, queries)
        result["char_count"] = len(entry)
        result["entry_index"] = i
        if result["verdict"] == "TRIM-SAFE":
            trim_safe.append(result)
        elif result["verdict"] == "POINTER":
            pointer_results.append(result)
        else:
            keep_hot.append(result)

    if not as_json:
        print(" " * 40, end="\r")  # clear progress line

    # Sort trim-safe by char_count descending (biggest savings first)
    trim_safe.sort(key=lambda r: -r["char_count"])

    total_chars_all = sum(len(e) for e in entries)
    trimmable_chars = sum(r["char_count"] for r in trim_safe)

    # ── Caps (live read) ──────────────────────────────────────────────────────
    try:
        import yaml
        cfg = yaml.safe_load(Path(os.path.join(HERMES_HOME, "config.yaml")).read_text())
        mem_cap = cfg.get("memory", {}).get("memory_char_limit", 3000)
    except Exception:
        mem_cap = 3000

    current_pct = round(100 * total_chars_all / mem_cap)
    projected_pct = round(100 * (total_chars_all - trimmable_chars) / mem_cap)

    output = {
        "summary": {
            "total_entries": len(entries),
            "probed": total,
            "already_pointer": len(pointer_entries),
            "trim_safe": len(trim_safe),
            "pointer_needed": len(pointer_results),
            "keep_hot": len(keep_hot),
            "trimmable_chars": trimmable_chars,
            "current_chars": total_chars_all,
            "cap": mem_cap,
            "current_pct": current_pct,
            "projected_pct_after_trim": projected_pct,
        },
        "TRIM-SAFE": trim_safe,
        "POINTER": pointer_results,
        "KEEP-HOT": keep_hot,
    }

    if as_json:
        print(json.dumps(output, indent=2))
        return

    # ── Human-readable report ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  MEMORY OFFLOAD PROBE REPORT")
    print(f"{'='*60}")
    s = output["summary"]
    print(f"  Entries: {s['total_entries']} total | {s['probed']} probed | {s['already_pointer']} already pointer-style")
    print(f"  Store: {s['current_chars']}/{s['cap']} chars ({s['current_pct']}%)")
    print(f"  After trim: projected {s['projected_pct_after_trim']}% ({s['trimmable_chars']} chars freed)")
    print()

    _VERDICT_ICONS = {"TRIM-SAFE": "✅", "POINTER": "🔸", "KEEP-HOT": "🔒"}

    for verdict, group in [("TRIM-SAFE", trim_safe), ("POINTER", pointer_results), ("KEEP-HOT", keep_hot)]:
        icon = _VERDICT_ICONS[verdict]
        print(f"── {icon} {verdict} ({len(group)}) {'─'*(40 - len(verdict))}─")
        if not group:
            print("  (none)")
        for r in group:
            fact_preview = r["fact"][:80].replace("\n", " ")
            print(f"  [{r['char_count']:4d} chars] {fact_preview}{'…' if len(r['fact']) > 80 else ''}")
            for q in r["queries"]:
                flag = "✓" if q["query_passed"] else "✗"
                print(f"           {flag} [{q['best_score']:.2f}] \"{q['query'][:55]}\"")
        print()

    print(f"  Total trimmable: {trimmable_chars} chars across {len(trim_safe)} entries.")
    print(f"{'='*60}\n")


# ── Probe mode ────────────────────────────────────────────────────────────────

def cmd_probe(knowledge_mod, fact: str, queries: Optional[list[str]], as_json: bool):
    auto = queries is None or len(queries) == 0
    if auto:
        queries = auto_queries(fact)
        if not as_json:
            print(f"Auto-generated queries:")
            for i, q in enumerate(queries, 1):
                print(f"  {i}. {q!r}")
            print()

    result = probe_fact(knowledge_mod, fact, queries)

    if as_json:
        print(json.dumps(result, indent=2))
        return

    icons = {"TRIM-SAFE": "✅", "POINTER": "🔸", "KEEP-HOT": "🔒"}
    verdict = result["verdict"]
    print(f"\nVerdict: {icons[verdict]} {verdict}")
    print(f"Fact:    {fact[:100]}")
    print()
    for q in result["queries"]:
        flag = "✓" if q["query_passed"] else "✗"
        match = "found" if q["fact_found"] else "not found"
        print(f"  {flag} [{q['best_score']:.3f}] {q['query']!r}  — fact {match} in top-3")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Probe hot-memory facts against Supabase knowledge store before trimming."
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    sub = parser.add_subparsers(dest="command")

    p_probe = sub.add_parser("probe", help="Probe a single fact")
    p_probe.add_argument("--fact", required=True)
    p_probe.add_argument("--queries", nargs="*", default=None)

    sub.add_parser("scan", help="Scan all MEMORY.md entries")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    t0 = time.time()
    knowledge_mod = _load_knowledge()

    if args.command == "probe":
        cmd_probe(knowledge_mod, args.fact, args.queries, args.as_json)
    elif args.command == "scan":
        cmd_scan(knowledge_mod, args.as_json)

    elapsed = time.time() - t0
    if not args.as_json:
        print(f"  (completed in {elapsed:.1f}s)\n")


if __name__ == "__main__":
    main()
