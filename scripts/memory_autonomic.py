#!/usr/bin/env python3
"""Memory Autonomic Maintenance — state reporter (deterministic trigger).

Runs each cron tick. Reports hot-store pressure and, when over threshold,
the offload-candidate entries ranked by suitability. Emits a CLEAN sentinel
when no action is needed so the agent can stay silent.

Thresholds:
  < OFFLOAD_AT  -> CLEAN (agent does nothing, stays silent)
  >= OFFLOAD_AT -> emit candidates; agent runs the offload doctrine
"""
import os, re, sys

HERMES = os.path.expanduser("~/.hermes")
MEM = f"{HERMES}/memories/MEMORY.md"
USR = f"{HERMES}/memories/USER.md"
MEM_CAP = 3000
USR_CAP = 1375
OFFLOAD_AT = 0.88   # trigger compaction when a store crosses 88% (keeps it from ever hitting the 90% ADD-block)

def chars(p):
    try:
        with open(p, encoding="utf-8") as f:
            return len(f.read())
    except FileNotFoundError:
        return 0

def entries(p):
    """Split a §-delimited store into (index, text, len) entries."""
    try:
        body = open(p, encoding="utf-8").read()
    except FileNotFoundError:
        return []
    parts = [e.strip() for e in body.split("§")]
    return [(i, e, len(e)) for i, e in enumerate(parts) if e]

# Heuristic offload-suitability: high score = better offload candidate.
# Stable infra detail (paths, model strings, topology) offloads well;
# operating rules / corrections / identity must STAY hot.
KEEP_HOT = re.compile(r"\b(NEVER|MUST|don't|do not|gate|approval|greenlight|lesson|clarify|"
                      r"compression-only|autonomous|doctrine|verif)", re.I)
OFFLOADABLE = re.compile(r"(knowledge\.py|~/\.hermes/|\.md\b|port \d|:\d{4}\b|"
                         r"deepseek|claude-|topology|cron \d|@\d)", re.I)

def score(text):
    s = len(text) / 100.0                      # bigger = more worth offloading
    if OFFLOADABLE.search(text): s += 3
    if KEEP_HOT.search(text):    s -= 6        # operating rule — keep hot
    if text.lower().startswith("user andrew"): s -= 99   # identity, never offload
    return s

mem_c, usr_c = chars(MEM), chars(USR)
mem_p, usr_p = mem_c / MEM_CAP, usr_c / USR_CAP

over = [(name, p, path) for name, p, path in
        (("MEMORY.md", mem_p, MEM), ("USER.md", usr_p, USR)) if p >= OFFLOAD_AT]

print(f"MEMORY.md {mem_c}/{MEM_CAP} ({mem_p*100:.0f}%) | USER.md {usr_c}/{USR_CAP} ({usr_p*100:.0f}%)")

if not over:
    print("CLEAN")          # sentinel — agent stays silent, no action
    sys.exit(0)

for name, p, path in over:
    if name == "USER.md":
        # USER.md is all load-bearing preference/identity facts — NOT offloadable to a
        # semantic store. The correct autonomic action is a cap-raise proposal, not offload.
        print(f"\nOVER THRESHOLD: {name} at {p*100:.0f}% — preferences are not offloadable.")
        print("ACTION=CAP_RAISE_PROPOSAL: USER.md holds operating preferences that must stay hot. "
              "Recommend raising memory.user_char_limit (gated config change) rather than offloading. "
              "Do a lossless compaction pass first; if still >90%, propose the cap bump.")
        continue
    print(f"\nOVER THRESHOLD: {name} at {p*100:.0f}% — needs compaction toward 80%")
    print("ACTION=OFFLOAD: store stable infra facts to Supabase (knowledge.py store) with a "
          "one-line hot pointer, VERIFY retrievable, back up MEMORY.md, THEN trim. Never silent-delete.")
    ranked = sorted(entries(path), key=lambda e: -score(e[1]))
    print("Top offload candidates (highest score first; verify-before-trim):")
    for idx, text, ln in ranked[:4]:
        if score(text) <= 0:
            continue
        print(f"  [entry {idx}, {ln} chars, score {score(text):.1f}] {text[:90].replace(chr(10),' ')}...")
