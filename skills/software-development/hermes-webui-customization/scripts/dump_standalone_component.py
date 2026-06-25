#!/usr/bin/env python3
"""
Dump the component JS + template structure from a bundled `.standalone.html`
design prototype so you can map its mock data BEFORE wiring real data.

Usage:
    python3 dump_standalone_component.py /path/to/file.standalone.html [outdir]

Writes <outdir>/component.js (the DCLogic Component class body) and prints a
summary of the mock data assignments you'll need to patch. See
references/standalone-bundle-data-wiring.md for the full wiring recipe.

Why byte-walk instead of regex: the inner HTML inside the __bundler/template
JSON string contains many literal </script> sequences; a non-greedy regex match
truncates the template to ~185 chars. Walk the JSON string honoring backslash
escapes to find its true closing quote.
"""
import json
import re
import sys
from pathlib import Path


def extract_template(html: str) -> str:
    """Return the decoded inner-HTML template string."""
    OPEN = '<script type="__bundler/template">'
    pos = html.find(OPEN)
    if pos < 0:
        raise SystemExit("no __bundler/template found — not a bundled standalone?")
    i = pos + len(OPEN)
    while i < len(html) and html[i] in " \t\n\r":
        i += 1
    if html[i] != '"':
        raise SystemExit("expected a JSON string after the template open tag")
    j = i + 1
    while j < len(html):
        ch = html[j]
        if ch == "\\":
            j += 2
            continue
        if ch == '"':
            j += 1
            break
        j += 1
    return json.loads(html[i:j])


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1]).read_text(errors="replace")
    outdir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp")
    outdir.mkdir(parents=True, exist_ok=True)

    template = extract_template(src)
    print(f"template inner-HTML: {len(template)} chars")

    scripts = list(re.finditer(r"<script[^>]*>(.*?)</script>", template, re.DOTALL))
    print(f"inner <script> tags: {len(scripts)}")
    # The component is usually the largest script body.
    comp = max(scripts, key=lambda m: len(m.group(1))).group(1)
    out = outdir / "component.js"
    out.write_text(comp)
    print(f"component JS: {len(comp)} chars -> {out}")

    print("\n=== mock data assignments to patch (each -> a window.__RD_* global) ===")
    # Class fields: NAME = [ ... ]   /   NAME = { ... }
    for m in re.finditer(r"^\s{2}([A-Z_][A-Z0-9_]*)\s*=\s*[\[{]", comp, re.M):
        print(f"  class field : {m.group(1)}")
    # In-render consts
    for m in re.finditer(r"\bconst\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*[\[{]", comp):
        name = m.group(1)
        if name[0].isupper() or name in ("agents", "memContent", "days"):
            print(f"  render const: {name}")

    print("\nNext: read component.js state={...}, the class fields above, and")
    print("renderVals() to see where each mock is consumed. One patch + one")
    print("__RD_* global per source. Recipe: standalone-bundle-data-wiring.md")


if __name__ == "__main__":
    main()
