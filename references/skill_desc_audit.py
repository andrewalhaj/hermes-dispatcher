#!/usr/bin/env python3
"""skill_desc_audit.py — Replicate upstream's `system_prompt_preview` locally.

The Hermes prompt index shows ONLY `name` + a description truncated to the
60-char cliff (agent/skill_utils.py:extract_skill_description):
    len(desc) <= 60  -> shown in full
    len(desc) >= 61  -> desc[:57] + "..."   (usable trigger surface = 57 chars)

There is no runtime skill retrieval (no embeddings/keyword match) and
`load_when:` is NOT rendered into the prompt. So name + <=57 chars of
description is the ENTIRE trigger surface the agent sees before deciding to
load a skill. This tool shows exactly what the agent will see and flags every
skill that loses trigger surface to truncation.

Usage:
    python3 skill_desc_audit.py                 # audit all skills, show offenders
    python3 skill_desc_audit.py --all           # list every skill (intact + truncated)
    python3 skill_desc_audit.py --check "desc"  # preview a single candidate description
    python3 skill_desc_audit.py --dir PATH      # override skills root (repeatable)
"""
from __future__ import annotations
import argparse, os, re, sys
from pathlib import Path

LIMIT = 60      # cliff: <= LIMIT shown whole
KEEP = 57       # >  LIMIT -> desc[:KEEP] + "..."
DEFAULT_DIRS = [
    os.path.expanduser("~/.hermes/skills"),
    "/usr/local/lib/hermes-agent/skills",
]

def render(desc: str) -> tuple[str, bool]:
    """Return (what_the_prompt_shows, was_truncated)."""
    desc = desc.strip().strip("'\"")
    if len(desc) > LIMIT:
        return desc[:KEEP] + "...", True
    return desc, False

def extract_desc(skill_md: Path) -> tuple[str, str]:
    """Return (name, raw_description) from a SKILL.md, handling folded YAML."""
    txt = skill_md.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^---\s*$(.*?)^---\s*$", txt, re.DOTALL | re.MULTILINE)
    fm = m.group(1) if m else txt[:2000]
    nm = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
    name = nm.group(1).strip() if nm else skill_md.parent.name
    dm = re.search(
        r"^description:\s*(?:[>|][-+]?\s*\n((?:[ \t]+.*\n?)+)|(.+))",
        fm, re.MULTILINE,
    )
    if not dm:
        return name, ""
    if dm.group(1):
        desc = " ".join(l.strip() for l in dm.group(1).splitlines()).strip()
    else:
        desc = dm.group(2).strip()
    return name, desc.strip().strip("'\"")

def collect(dirs):
    rows = []
    seen_files = set()
    for d in dirs:
        root = Path(d)
        if not root.exists():
            continue
        for f in root.rglob("SKILL.md"):
            rp = str(f.resolve())
            if rp in seen_files:
                continue
            seen_files.add(rp)
            # skip excluded dirs
            if any(part in {".git", "node_modules", "__pycache__", ".venv", "venv"}
                   for part in f.parts):
                continue
            name, desc = extract_desc(f)
            rows.append((name, desc, f))
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--check", metavar="DESC")
    ap.add_argument("--dir", action="append", default=[])
    args = ap.parse_args()

    if args.check is not None:
        shown, trunc = render(args.check)
        n = len(args.check.strip().strip("'\""))
        print(f"input length : {n} chars")
        print(f"truncated    : {'YES — loses tail past char 57' if trunc else 'no — shown in full'}")
        print(f"agent sees   : {shown!r}")
        if trunc:
            lost = args.check.strip().strip("'\"")[KEEP:]
            print(f"LOST tail    : {lost!r}")
        sys.exit(0)

    dirs = args.dir or DEFAULT_DIRS
    rows = collect(dirs)
    rows.sort(key=lambda r: -len(r[1]))
    over = [r for r in rows if len(r[1]) > LIMIT]
    ok = [r for r in rows if len(r[1]) <= LIMIT]

    print(f"Skills scanned : {len(rows)}  (dirs: {', '.join(dirs)})")
    print(f"TRUNCATED >{LIMIT}  : {len(over)}  ({100*len(over)//max(len(rows),1)}% lose trigger surface)")
    print(f"Intact   <={LIMIT}  : {len(ok)}")
    print()
    print("=== TRUNCATED — what the agent actually sees vs what was lost ===")
    for name, desc, f in over:
        shown, _ = render(desc)
        lost = desc[KEEP:]
        print(f"\n[{len(desc):>3}] {name}")
        print(f"   SEES: {shown}")
        print(f"   LOST: {lost[:90]}{'…' if len(lost) > 90 else ''}")
    if args.all:
        print("\n=== INTACT (<=60, shown whole) ===")
        for name, desc, f in sorted(ok, key=lambda r: -len(r[1])):
            print(f"  [{len(desc):>2}] {name}: {desc}")

if __name__ == "__main__":
    main()
