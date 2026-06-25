#!/usr/bin/env python3
"""
skill-desc-audit.py — replicate the system-prompt skill-description truncation
and flag every skill whose trigger surface is being clipped.

WHY: agent/skill_utils.py:extract_skill_description() does:
        if len(desc) > 60: return desc[:57] + "..."
        return desc
     i.e. a CLIFF at 60 — <=60 shows whole, >=61 loses everything past char 57.
     The agent only fires a skill if the trigger keyword lands in the visible
     window. This tool shows EXACTLY what the prompt renders, so descriptions
     can be authored/fixed to keep the trigger inside the budget.

USAGE:
  python3 skill-desc-audit.py                # audit all skills (profile + builtin)
  python3 skill-desc-audit.py --offenders    # only the truncated ones
  python3 skill-desc-audit.py <skill-name>   # preview ONE skill (like the merged
                                             #   system_prompt_preview feature)
"""
import os, re, sys, glob

LIMIT = 60          # the cliff
KEEP = 57           # chars kept before the ellipsis
SCAN_DIRS = [
    os.path.expanduser("~/.hermes/skills"),
    "/usr/local/lib/hermes-agent",   # builtin skills live under here
]

def render(desc: str) -> str:
    """Byte-for-byte replica of extract_skill_description()."""
    desc = str(desc).strip().strip("'\"")
    if not desc:
        return ""
    if len(desc) > LIMIT:
        return desc[:KEEP] + "..."
    return desc

def parse_skill(path: str):
    txt = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r'^---\s*$(.*?)^---\s*$', txt, re.DOTALL | re.MULTILINE)
    fm = m.group(1) if m else txt[:2000]
    name_m = re.search(r'^name:\s*(.+)$', fm, re.MULTILINE)
    # description: single-line OR folded (>- / |)
    dm = re.search(
        r'^description:\s*(?:[>|][-+]?\s*\n((?:[ \t]+.*\n?)+)|(.+))',
        fm, re.MULTILINE)
    if dm and dm.group(1):
        desc = " ".join(l.strip() for l in dm.group(1).splitlines()).strip()
    elif dm:
        desc = dm.group(2).strip()
    else:
        desc = ""
    desc = desc.strip().strip("'\"")
    name = name_m.group(1).strip() if name_m else os.path.basename(os.path.dirname(path))
    return name, desc, path

def collect():
    seen, rows = set(), []
    for base in SCAN_DIRS:
        for f in glob.glob(base + "/**/SKILL.md", recursive=True):
            if any(seg in f for seg in ("/.git/", "/venv/", "/node_modules/", "/__pycache__/")):
                continue
            name, desc, path = parse_skill(f)
            if name in seen:
                continue
            seen.add(name)
            rows.append((name, desc, path))
    return rows

def main():
    args = [a for a in sys.argv[1:]]
    rows = collect()

    # single-skill preview mode
    targets = [a for a in args if not a.startswith("-")]
    if targets:
        want = targets[0]
        hit = [r for r in rows if r[0] == want]
        if not hit:
            print(f"No skill named {want!r} found.")
            sys.exit(1)
        name, desc, path = hit[0]
        n = len(desc)
        print(f"skill:        {name}")
        print(f"file:         {path}")
        print(f"desc length:  {n} chars  ({'TRUNCATED' if n > LIMIT else 'intact'})")
        print(f"FULL:         {desc}")
        print(f"PROMPT SHOWS: {render(desc)}")
        if n > LIMIT:
            print(f"LOST TAIL:    ...{desc[KEEP:]}")
            print(f"\n  -> Move the trigger keyword into the first {KEEP} chars,")
            print(f"     or shorten to <= {LIMIT} so it shows whole.")
        sys.exit(0)

    offenders_only = "--offenders" in args
    over = [r for r in rows if len(r[1]) > LIMIT]
    intact = [r for r in rows if 0 < len(r[1]) <= LIMIT]
    empty = [r for r in rows if not r[1]]

    print(f"TOTAL skills scanned: {len(rows)}")
    print(f"TRUNCATED (>{LIMIT}, trigger surface clipped): {len(over)}  "
          f"({100*len(over)//max(len(rows),1)}%)")
    print(f"INTACT (<= {LIMIT}): {len(intact)}")
    if empty:
        print(f"NO DESCRIPTION: {len(empty)}  -> {', '.join(r[0] for r in empty)}")
    print()

    print("=== TRUNCATED (full len | what the prompt shows | lost tail) ===")
    for name, desc, _ in sorted(over, key=lambda r: -len(r[1])):
        print(f"\n[{len(desc):>3}] {name}")
        print(f"   SHOWS: {render(desc)}")
        print(f"   LOST:  ...{desc[KEEP:][:80]}{'…' if len(desc) > KEEP+80 else ''}")

    if not offenders_only:
        print("\n=== INTACT (already <= 60 — good triggers) ===")
        for name, desc, _ in sorted(intact, key=lambda r: -len(r[1])):
            print(f"  [{len(desc):>2}] {name}: {desc}")

if __name__ == "__main__":
    main()
