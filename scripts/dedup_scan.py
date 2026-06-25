#!/usr/bin/env python3
"""Knowledge DB Dedup Scanner — detect near-duplicate facts.

REPORT-ONLY: this script never mutates the knowledge DB. It reads, scores in
memory, and prints. Exits 0 always — finding duplicates is a normal result,
not a failure (so the watchdog never flags a successful scan).

Scoring note (the important part): every stored fact carries a
"This passage is from …: <title> > <section>." contextual prefix. That prefix
is deliberate (improves retrieval) but it is IDENTICAL across all chunks of one
source doc, so it inflates cosine similarity between otherwise-distinct chunks.
For DEDUP SCORING ONLY we re-embed the prefix-stripped text in memory; the
stored vectors are never read or altered, so retrieval quality is unaffected.

Output tiers:
  HIGH   (>= 0.95) — near-identical text; review for deletion.
  REVIEW (0.85-0.95) — related; usually fine, eyeball before acting.
Each pair is annotated:
  [same-source] — both chunks share a source tag. Usually two sections of ONE
                  doc (NOT a dup) — unless the whole doc was ingested twice,
                  which shows up as a same-source HIGH pair.
  [cross-doc]   — different source docs; a HIGH cross-doc pair is a real
                  redundant note worth collapsing.

Backend: Supabase pgvector (migrated from LanceDB).

Usage:
  python3 dedup_scan.py
  python3 dedup_scan.py --threshold 0.88
  python3 dedup_scan.py --full-report   # print even if clean
"""
import os, sys, json, time, re

# -- venv self-guard -----------------------------------------------------
# Cron (no_agent) launches this with bare system python3, which lacks
# numpy/sentence_transformers. Re-exec under the Hermes venv if missing.
try:
    import numpy  # noqa: F401
except ModuleNotFoundError:
    _VENV_PY = "/usr/local/lib/hermes-agent/venv/bin/python"
    if os.path.exists(_VENV_PY) and os.path.realpath(sys.executable) != os.path.realpath(_VENV_PY):
        os.execv(_VENV_PY, [_VENV_PY] + sys.argv)
    raise

import numpy as np
from sentence_transformers import SentenceTransformer

SIMILARITY_THRESHOLD = 0.85   # floor for what gets reported
HIGH_TIER = 0.95              # >= this is the "review for deletion" tier

# -- lazy model load -----------------------------------------------------
_model = None

def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model

_PREFIX_RE = re.compile(r'^This passage is from\b')

def strip_context_prefix(text):
    """Remove the leading 'This passage is from …: <title> > <section>.' line.
    Returns the chunk's real content for scoring. Falls back to the original
    text if the pattern isn't present or stripping would empty it."""
    if isinstance(text, str) and _PREFIX_RE.match(text):
        idx = text.find("\n\n")
        if idx != -1:
            stripped = text[idx + 2:].strip()
            if stripped:
                return stripped
    return text

def load_all_facts():
    """Read all facts (text + tags) from Supabase. Read-only."""
    import importlib.util
    _kb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge.py')
    spec = importlib.util.spec_from_file_location('knowledge', _kb_path)
    kb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kb)
    client = kb.get_db()
    resp = client.table('knowledge').select(
        'id,text,tags,priority,stored_at'
    ).execute()
    facts = []
    for row in (resp.data or []):
        facts.append({
            'id': row['id'],
            'text': row['text'],
            'tags': kb._parse_tags(row.get('tags', [])),
            'priority': row.get('priority', 'normal'),
            'stored_at': kb._parse_stored_at(row.get('stored_at')),
        })
    return facts

def _same_source(a, b):
    return bool(set(a['tags']) & set(b['tags']))

def find_duplicates(facts, threshold):
    """Re-embed prefix-stripped text IN MEMORY and score pairwise.
    Stored vectors are never touched. Returns (score, a, b, same_source)."""
    n = len(facts)
    model = get_model()
    stripped = [strip_context_prefix(f['text']) for f in facts]
    vecs = np.asarray(model.encode(stripped, show_progress_bar=False), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vecs = vecs / norms
    sim = np.dot(vecs, vecs.T)

    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            score = float(sim[i, j])
            if score >= threshold:
                pairs.append((score, facts[i], facts[j], _same_source(facts[i], facts[j])))
    pairs.sort(key=lambda x: x[0], reverse=True)
    return pairs

def _snippet(text):
    return strip_context_prefix(text)[:160].replace('\n', ' ')

def _fmt_pair(idx, score, a, b, src):
    tag = "same-source" if src else "cross-doc"
    return [
        f"### {idx}. similarity {score:.3f} · [{tag}]",
        f"- **A** `{a['id']}` [{a['priority']}] tags: {', '.join(a['tags'])}",
        f"  > {_snippet(a['text'])}",
        f"- **B** `{b['id']}` [{b['priority']}] tags: {', '.join(b['tags'])}",
        f"  > {_snippet(b['text'])}",
        "",
    ]

def format_report(pairs, total):
    high = [p for p in pairs if p[0] >= HIGH_TIER]
    review = [p for p in pairs if p[0] < HIGH_TIER]

    lines = []
    lines.append(f"# Knowledge DB Dedup Scan — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}")
    lines.append(
        f"Scored on prefix-stripped text · {total} facts · "
        f"{len(pairs)} pair(s) >= {SIMILARITY_THRESHOLD:.2f} "
        f"({len(high)} HIGH >= {HIGH_TIER:.2f}, {len(review)} REVIEW)\n"
    )

    lines.append(f"## HIGH >= {HIGH_TIER:.2f} — near-identical, review for deletion")
    if high:
        lines.append("_same-source HIGH = possibly a whole doc ingested twice (real dup); "
                     "cross-doc HIGH = redundant note worth collapsing._\n")
        for i, (s, a, b, src) in enumerate(high, 1):
            lines += _fmt_pair(i, s, a, b, src)
    else:
        lines.append("_none_\n")

    lines.append(f"## REVIEW {SIMILARITY_THRESHOLD:.2f}-{HIGH_TIER:.2f} — related, usually fine")
    if review:
        lines.append("_mostly adjacent chunks of one doc; do NOT delete without reading both._\n")
        for i, (s, a, b, src) in enumerate(review, 1):
            lines += _fmt_pair(i, s, a, b, src)
    else:
        lines.append("_none_\n")

    lines.append("> Before deleting anything: `python3 ~/.hermes/scripts/knowledge.py search "
                 "\"<concept>\"`. Same-source REVIEW pairs are normal chunking, not duplicates.")
    return '\n'.join(lines)

def main():
    threshold = SIMILARITY_THRESHOLD
    full_report = False

    args = sys.argv[1:]
    while args:
        if args[0] == '--threshold' and len(args) > 1:
            threshold = float(args[1])
            args = args[2:]
        elif args[0] == '--full-report':
            full_report = True
            args = args[1:]
        else:
            args = args[1:]

    facts = load_all_facts()
    if len(facts) < 2:
        if full_report:
            print(f"Knowledge DB: {len(facts)} facts — nothing to compare.")
        sys.exit(0)

    pairs = find_duplicates(facts, threshold)

    if pairs:
        print(format_report(pairs, len(facts)))
    elif full_report:
        print(f"Knowledge DB: {len(facts)} facts — no pairs >= {threshold:.2f}")
    # else: silent (watchdog pattern)

    sys.exit(0)

if __name__ == '__main__':
    main()
