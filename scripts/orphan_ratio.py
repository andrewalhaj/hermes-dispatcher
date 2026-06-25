#!/usr/bin/env python3
"""
orphan_ratio.py — measure pointer-coverage of the Supabase cold store.
=====================================================================
Read-only. Counts cold facts that have NO cue in the hot tier (MEMORY.md) —
"orphan facts" that B-lite's judgment-fired search can never reliably surface.

WHY THIS EXISTS (2026-06-09)
----------------------------
B-lite retrieval is reliable only while pointer coverage stays high. Automated/
fast cold-store growth can store rows WITHOUT leaving a hot-tier pointer, creating
orphans. The crossover signal to B-full is NOT row count — it's pointer-coverage
DECAY. This script makes that decay measurable instead of guessed.

WHAT COUNTS AS "POINTED-TO" (a row is NOT an orphan if ANY holds)
-----------------------------------------------------------------
  1. Its 8-char row id appears verbatim in MEMORY.md.
  2. Its `source` doc basename appears in MEMORY.md (e.g. infrastructure-summary).
  3. A `knowledge.py search "<q>"` pointer in MEMORY.md has query-terms that
     overlap the row's key terms by >= OVERLAP_MIN (the pointer would cue it).
  4. Topic-term overlap: >= OVERLAP_MIN of the row's salient terms appear
     anywhere in MEMORY.md (a plain hot mention is itself a cue).

Only "substantive" rows are scored — session-changelog / dated-archive dumps are
excluded (they're frozen history, not facts meant to be cue-retrieved).

USAGE
-----
  python3 ~/.hermes/scripts/orphan_ratio.py            # human report
  python3 ~/.hermes/scripts/orphan_ratio.py --json     # {ratio,total,orphans,...}
  python3 ~/.hermes/scripts/orphan_ratio.py --quiet    # just the ratio float

Exit 0 always (it's a measurement, not a gate). The watchdog decides thresholds.
"""
import json
import os
import re
import sys

HERMES = os.path.expanduser("~/.hermes")
MEMORY_PATH = os.path.join(HERMES, "memories", "MEMORY.md")
sys.path.insert(0, os.path.join(HERMES, "scripts"))

OVERLAP_MIN = 2          # row is "cued" if >=2 salient terms are reachable from hot
MIN_TERM_LEN = 4         # ignore short/noise tokens
# Rows whose ONLY tag matches these (frozen historical dumps) are not scored.
ARCHIVE_TAG_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # e.g. "2026-06-02"
# Sources that are frozen historical/internal dumps, NOT facts meant to be
# cue-retrieved by B-lite. Excluded from the orphan score (they have no business
# being pointed-to from MEMORY.md). Matched against the row's source basename.
ARCHIVE_SOURCE_RE = re.compile(
    r"(state$|snapshot|changelog|user-model|peer-card|session|-archive|backup)",
    re.IGNORECASE,
)
STOP = frozenset(
    "the a an and or of to for with in on at by is are be this that from per "
    "via use using session hermes andrew memory fact facts store stored note "
    "june full key outcome source model telegram".split()
)


def tokenize(text):
    out = set()
    for w in re.findall(r"[a-z0-9][a-z0-9\-]+", (text or "").lower()):
        w = w.strip("-")
        if len(w) >= MIN_TERM_LEN and w not in STOP:
            out.add(w)
    return out


def salient_terms(row):
    """Key terms identifying a row — first ~120 chars of text + source basename."""
    text = (row.get("text") or "")
    head = text[:120]
    src = os.path.basename(str(row.get("source") or "")).replace(".md", "")
    return tokenize(head + " " + src)


def is_archive_dump(row):
    """Frozen historical/internal row not meant for cue-retrieval (changelogs,
    state snapshots, Honcho user-model/peer-card dumps, dated archives)."""
    src = os.path.basename(str(row.get("source") or "")).replace(".md", "")
    if src and ARCHIVE_SOURCE_RE.search(src):
        return True
    tags = row.get("tags")
    if tags is None:
        return False
    try:
        taglist = list(tags)
    except TypeError:
        taglist = [tags]
    taglist = [str(t) for t in taglist]
    if taglist and all(ARCHIVE_TAG_RE.match(t) for t in taglist):
        # dated-only tags AND a changelog/session-shaped head → archive
        head = (row.get("text") or "")[:80].lower()
        if any(k in head for k in ("changelog", "session ", "session:", "outage",
                                   "snapshot", "state snapshot")):
            return True
    return False


def load_rows():
    """Read cold rows from the Supabase knowledge store via knowledge.py's
    paginated REST fetch (no embedding-model load) so this stays cheap enough
    to run from the 15-min watchdog."""
    import knowledge as k
    rows = k._supa_all_rows(select="id,text,tags,source,priority")
    cols = ("id", "text", "tags", "source", "priority")
    return [{c: r.get(c) for c in cols if c in r} for r in rows]


def is_doc_chunk(row):
    """A chunk of a larger reference document (has a real doc source basename).
    Coverage for these is a DOCUMENT-level question (is the doc pointed-to?),
    NOT a per-chunk one — counting each chunk as an orphan is a category error."""
    src = os.path.basename(str(row.get("source") or "")).replace(".md", "")
    if not src or src.lower() == "cli-input":
        return False
    return True


# Stale session-progress junk that should never have been stored as a "fact"
# (memory doctrine: no task progress / session outcomes in the store). These are
# prune candidates, NOT orphans to be pointered. Flagged separately.
STALE_PROGRESS_RE = re.compile(
    r"(changed hot memory|shrunk hot memory|hot memory (from|to|at)|"
    r"\d+\s*entries at \d+%|at \d+% capacity|built .{0,30}script|"
    r"bootstrapped lancedb|shrunk .{0,20}to \d+ chars)",
    re.IGNORECASE,
)


def compute(verbose=False):
    """Segmented pointer-coverage measurement. Returns TWO distinct metrics:

    - fact_ratio: orphan STANDALONE facts / total standalone facts. THIS is the
      B-lite reliability metric — a standalone fact with no hot cue is genuinely
      lost. The watchdog tracks this one.
    - doc_coverage: covered reference-DOCUMENTS / total documents, measured at
      the document level (a doc is covered if its name is reachable from the hot
      tier OR a skill). Multi-chunk docs don't each need a MEMORY.md pointer.

    Stale session-progress junk is flagged separately as prune candidates, not
    counted as orphans (it shouldn't be in the store at all).
    """
    rows = load_rows()
    try:
        with open(MEMORY_PATH, encoding="utf-8") as f:
            mem = f.read()
    except FileNotFoundError:
        mem = ""
    mem_low = mem.lower()
    mem_terms = tokenize(mem)

    def cued(row):
        rid = str(row.get("id") or "")
        src = os.path.basename(str(row.get("source") or "")).replace(".md", "")
        if rid and rid in mem_low:
            return True
        if src and len(src) >= MIN_TERM_LEN and src.lower() in mem_low:
            return True
        terms = salient_terms(row)
        return bool(terms and len(terms & mem_terms) >= OVERLAP_MIN)

    fact_orphans = []
    facts_scored = 0
    stale = []
    docs_seen = {}          # doc basename -> covered? (OR across its chunks)
    skipped = 0

    for row in rows:
        if is_archive_dump(row):
            skipped += 1
            continue
        head = (row.get("text") or "")[:70].replace("\n", " ")
        if is_doc_chunk(row):
            src = os.path.basename(str(row.get("source") or "")).replace(".md", "")
            docs_seen[src] = docs_seen.get(src, False) or cued(row)
            continue
        # standalone fact
        if STALE_PROGRESS_RE.search(row.get("text") or ""):
            stale.append({"id": str(row.get("id") or ""), "head": head})
            continue
        facts_scored += 1
        if not cued(row):
            fact_orphans.append({
                "id": str(row.get("id") or ""),
                "source": "(none)",
                "head": head,
            })

    fact_ratio = (len(fact_orphans) / facts_scored) if facts_scored else 0.0
    total_docs = len(docs_seen)
    covered_docs = sum(1 for v in docs_seen.values() if v)
    doc_coverage = (covered_docs / total_docs) if total_docs else 1.0

    return {
        # headline B-lite metric (this is what the watchdog tracks)
        "ratio": round(fact_ratio, 3),
        "orphans": len(fact_orphans),
        "scored": facts_scored,
        # secondary: document-level coverage
        "doc_coverage": round(doc_coverage, 3),
        "docs_total": total_docs,
        "docs_covered": covered_docs,
        # hygiene: stale junk that should be pruned, not pointered
        "stale_prune_candidates": len(stale),
        "skipped_archive": skipped,
        "orphan_rows": fact_orphans if verbose else fact_orphans[:10],
        "stale_rows": stale if verbose else stale[:10],
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    res = compute(verbose=("--json" in args or "--all" in args))
    if "--quiet" in args:
        print(res["ratio"])
    elif "--json" in args:
        print(json.dumps(res))
    else:
        print(f"Fact-orphan ratio: {res['ratio']:.1%}  "
              f"({res['orphans']} uncued / {res['scored']} standalone facts)  "
              f"← B-lite reliability metric (watchdog tracks this)")
        print(f"Doc coverage:      {res['doc_coverage']:.1%}  "
              f"({res['docs_covered']}/{res['docs_total']} reference docs reachable)")
        print(f"Stale prune-bait:  {res['stale_prune_candidates']} rows  "
              f"(session-progress junk — prune, don't pointer)")
        print(f"Archive skipped:   {res['skipped_archive']} rows")
        if res["orphan_rows"]:
            print("\nUncued standalone facts (these genuinely need a hot-tier pointer):")
            for o in res["orphan_rows"]:
                print(f"  [{o['id']}] {o['head']}")
            print("\nFix: add a one-line MEMORY.md pointer for any TRUE fact above. "
                  "Pointer = the B-lite cue.")
        if res.get("stale_rows"):
            print("\nStale prune candidates (should not be in the store at all):")
            for s in res["stale_rows"]:
                print(f"  [{s['id']}] {s['head']}")
    sys.exit(0)
