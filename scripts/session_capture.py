#!/usr/bin/env python3
"""Session Capture — extract learnable facts from session text and store to Supabase.

Usage:
  python3 session_capture.py "<session exchange text>"
  echo "text" | python3 session_capture.py --stdin
  
The script uses lightweight heuristics to identify facts worth storing:
  • Config changes, new integrations, bug fixes, corrections, decisions
  • Session summaries and changelogs are auto-indexed section by section
  
Dedup is done against the existing Supabase store via knowledge.search().
If a fact's top semantic match scores above SIMILARITY_THRESHOLD, it's skipped.
"""

import os, sys, json, time, uuid, re

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)
from knowledge import store, search, count_facts, get_model, embed

SIMILARITY_THRESHOLD = 0.92  # Semantic similarity above which we skip as duplicate (0-1)
MIN_FACT_LENGTH = 25

# --- Fact extraction heuristics ---

# Match sentences starting with action verbs or containing key action patterns
FACTUALLY = re.compile(r"""
    (?:^|[.!?]\s+|(?<=[.!?])\s+)
    (
        (?:Changed|Fixed|Added|Removed|Created|Updated|Set\s+up|Switched|Upgraded|Downgraded|
         Patched|Reset|Reconfigured|Migrated|Installed|Uninstalled|Deployed|Retired|
         Corrected|Replaced|Renamed|Moved|Archived|Restored|Enabled|Disabled|
         Built|Bootstrapped|Seeded|Generated|Wrote|Compacted|Extended|Wired|Hooked\s+up|
         Connected|Indexed|Stored|Captured|Exported|Verified|Confirmed|Shrunk)
        \s.{10,}?(?:[.!?]|$)
    )
""", re.IGNORECASE | re.VERBOSE)

DECISIONS = re.compile(r"""
    (?:^|[.!?]\s+|(?<=[.!?])\s+)
    (
        (?:Decision|Chose|Selected|Opted|Went\s+with|Picked|Settled\s+on|Decided)
        \s.{10,}?(?:[.!?]|$)
    )
""", re.IGNORECASE | re.VERBOSE)

CORRECTIONS = re.compile(r"""
    (?:^|[.!?]\s+|(?<=[.!?])\s+)
    (
        (?:Should\s+have|Instead\s+of|Rather\s+than|Corrected|Misunderstood|Clarified)
        \s.{10,}?(?:[.!?]|$)
    )
""", re.IGNORECASE | re.VERBOSE)

COMMAND_PATTERNS = re.compile(r"""
    (?:^|[.!?]\s+)
    (
        [A-Z][^.?!]*?
        (?:`|')(python3|pip|hermes|curl|git|docker|apt|npm|tar|ssh)\s[^`'\n]+(?:`|')
        .{0,100}?(?:[.?!]|$)
    )
""", re.IGNORECASE | re.VERBOSE)

CONFIG_PATTERNS = re.compile(r"""
    (\w+(?:\.\w+)*)\s*(?:→|->|set\s+to|=)\s*(['"\w\-./:]+)
""", re.IGNORECASE)

# --- Main logic ---

def extract_facts(text):
    """Run all heuristics and return deduplicated factoids."""
    facts = []

    # Pattern-based extraction
    for pattern, tag in [
        (FACTUALLY, 'change'),
        (DECISIONS, 'decision'),
        (CORRECTIONS, 'correction'),
    ]:
        for match in pattern.finditer(text):
            fact = match.group(1).strip()
            if len(fact) >= MIN_FACT_LENGTH:
                facts.append((fact, tag))

    # Extract commands with explanations
    for match in COMMAND_PATTERNS.finditer(text):
        cmd = match.group(0).strip()
        if match.lastindex and match.lastindex >= 2 and match.group(2):
            cmd = f"{match.group(1).strip()} — {match.group(2).strip()}"
        if len(cmd) >= MIN_FACT_LENGTH:
            facts.append((cmd, 'command'))

    # Extract config changes  
    for match in CONFIG_PATTERNS.finditer(text):
        key, val = match.group(1).strip(), match.group(2).strip()
        fact = f"Config: {key} = {val}"
        if len(fact) >= MIN_FACT_LENGTH:
            facts.append((fact, 'config'))

    return facts

def is_duplicate(text, threshold=0.92):
    """Check if a fact is already in Supabase (semantic dedup via knowledge.search)."""
    existing = search(text, top_k=3)
    if not existing:
        return False
    # knowledge.search() returns hits sorted by 'score' (higher is closer, 0-1).
    best_score = existing[0].get('score', 0)
    return best_score > threshold

def capture_session(text, dry_run=False):
    """Main entry point: extract and store facts from session text."""
    facts = extract_facts(text)
    
    if not facts:
        return {'stored': 0, 'skipped': 0, 'facts': []}

    results = []
    stored = 0
    skipped = 0

    for fact, tag in facts:
        if is_duplicate(fact, SIMILARITY_THRESHOLD):
            skipped += 1
            if dry_run:
                results.append({'fact': fact, 'status': 'skipped (duplicate)', 'tag': tag})
            continue
        
        if not dry_run:
            fid = store(fact, tags=[tag, 'auto-captured'], priority='normal')
            results.append({'fact': fact, 'status': f'stored ({fid})', 'tag': tag})
        else:
            results.append({'fact': fact, 'status': 'would store', 'tag': tag})
        stored += 1

    return {'stored': stored, 'skipped': skipped, 'facts': results}

# --- CLI ---

if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    if dry_run:
        sys.argv.remove('--dry-run')

    if '--stdin' in sys.argv:
        text = sys.stdin.read()
        sys.argv.remove('--stdin')
    elif len(sys.argv) > 1:
        text = ' '.join(sys.argv[1:])
    else:
        print("Usage: session_capture.py [--dry-run] <text> | --stdin")
        print("       Extracts learnable facts and stores them to Supabase")
        print("       --dry-run: preview only, don't store")
        sys.exit(1)

    result = capture_session(text, dry_run=dry_run)
    print(f"Extracted {len(result['facts'])} facts: {result['stored']} stored, {result['skipped']} skipped (duplicates)")
    if result['facts']:
        print()
        for f in result['facts']:
            print(f"  [{f['tag']}] {f['status']}")
            print(f"    {f['fact'][:200]}")
            print()
