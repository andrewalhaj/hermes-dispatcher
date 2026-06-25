#!/usr/bin/env python3
"""
Calibration tests for skill_review_checkpoint.py (the per-session skill-sweep guard).
====================================================================================
Run BEFORE committing any edit to the checkpoint module, AND after a core update
(to confirm the live module still behaves):

    /usr/local/lib/hermes-agent/venv/bin/python \
        ~/.hermes/patches/test_skill_review_checkpoint.py

Exit 0 = all green. Non-zero = regression; do NOT ship the edit / restart.

This is the REUSABLE TEMPLATE. The live copy lives at
~/.hermes/patches/test_skill_review_checkpoint.py. Adapt the fixtures when you
build a new guard. It locks the two defects found 2026-06-09:
  1. The motivating LanceDB prompt scored complex=False (shared threshold too
     high; fix = decoupled SR_SIGNALS + SR_THRESHOLD=1).
  2. The matcher returned the wrong skill (ignored tags + glued hyphens; fix =
     read tags, split hyphens, weight tags+name 3x over description).
Both must stay fixed.
"""
import sys
import os

sys.path.insert(0, os.path.expanduser("~/.hermes/patches"))
import skill_review_checkpoint as s  # noqa: E402

FAILS = []


def check(label, cond):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}")
    if not cond:
        FAILS.append(label)


# Complexity gate ------------------------------------------------------------
print("Complexity classifier:")
COMPLEX = [
    # The motivating failure — MUST fire now.
    "build a lancedb prototype for semantic skill discovery and wire it into the gateway",
    "audit and refactor the memory architecture across all profiles",
    "set up a new cron to self-heal the patch guard",
    "diagnose the delegation 401 and fix the root cause",
    "integrate a vector index for semantic search",
]
SIMPLE = ["hi", "thanks", "what time is it", "test"]
for t in COMPLEX:
    check(f"complex: {t[:50]!r}", s._is_complex(t.lower()) is True)
for t in SIMPLE:
    check(f"simple:  {t[:50]!r}", s._is_complex(t.lower()) is False)

# Skill matcher --------------------------------------------------------------
print("\nSkill matcher (must surface the right domain skill):")
EXPECT = [  # (prompt, skill-that-MUST-appear-in-top-3)
    ("build a lancedb prototype for semantic skill discovery", "knowledge-store"),
    ("audit and compact the memory hot tier", "memory-discipline"),
    ("reduce hermes token spend and model routing cost", "token-optimization"),
]
for prompt, must in EXPECT:
    got = s._match_skills(prompt.lower())
    check(f"{prompt[:42]!r} -> contains {must!r} (got {got})", must in got)

# Nudge formatting -----------------------------------------------------------
print("\nNudge formatting:")
msgs = [{"role": "tool", "content": "tool output"}]
ok = s._append_nudge(msgs, ["knowledge-store", "memory-discipline"])
check("append_nudge returns True on a tool message", ok is True)
check("nudge text appended", "knowledge-store" in msgs[-1]["content"])
check("generic fallback when no candidates",
      s._append_nudge([{"role": "tool", "content": "x"}], []) is True)

# Summary --------------------------------------------------------------------
print()
if FAILS:
    print(f"RESULT: {len(FAILS)} FAILURE(S): {FAILS}")
    sys.exit(1)
print("RESULT: ALL GREEN")
sys.exit(0)
