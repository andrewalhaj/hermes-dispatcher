#!/usr/bin/env python3
"""
Static structural-balance audit for the DC/bundler standalone after a redesign
panel-swap patch. Run it AFTER editing _redesign_patches.py and BEFORE the gated
hermes-webui restart. Catches the "panels emitted outside #hermes-shell" runtime bug
(nav clicks don't switch panels / every panel but the first is blank) WITHOUT needing
CDP — it proves whether the patched template's <div>/<sc-if> nesting is balanced and
whether every panel sc-if lands at the same depth.

USAGE (from the served project dir, e.g. /root/projects/hermes-webui-new):
    HERMES_HOME=/root/.hermes /usr/local/lib/hermes-agent/venv/bin/python \
        scripts/audit_template_balance.py [PROJECT_DIR]

Exits 0 if balanced and all main panels share one depth; non-zero otherwise.

See references/dc-runtime-debugging.md for the full root-cause writeup (orphaned-tail
panel swap: a patch OLD that covers only part of the original <sc-if> block).
"""
import sys, os, re, json

proj = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
sys.path.insert(0, proj)

import server as srv  # the served project's server.py


def extract_template(html: str) -> str:
    """Byte-walk the __bundler/template JSON string and decode it (same boundary
    walk _patch_standalone uses, so <\\/script> inside the value doesn't confuse us)."""
    OPEN_TAG = '<script type="__bundler/template">'
    pos = html.find(OPEN_TAG)
    if pos < 0:
        raise SystemExit("ERROR: __bundler/template not found")
    i = pos + len(OPEN_TAG)
    while i < len(html) and html[i] in ' \t\n\r':
        i += 1
    j = i + 1
    while j < len(html):
        ch = html[j]
        if ch == '\\':
            j += 2
            continue
        if ch == '"':
            j += 1
            break
        j += 1
    return json.loads(html[i:j])


def find_scif_block(t: str, marker: str):
    """Return (start, end) of the marker's <sc-if>...</sc-if> by depth-counting."""
    start = t.find(marker)
    if start == -1:
        return -1, -1
    depth = 0
    i = start
    while i < len(t):
        if t[i:i + 7] == '<sc-if ':
            depth += 1
            i += 7
        elif t[i:i + 8] == '</sc-if>':
            depth -= 1
            if depth == 0:
                return start, i + 8
            i += 8
        else:
            i += 1
    return start, -1


def main() -> int:
    raw = srv.STANDALONE_PATH.read_text(errors='replace')
    patched_html = srv._patch_standalone(raw)
    t = extract_template(patched_html)

    div_open, div_close = t.count('<div'), t.count('</div>')
    scif_open, scif_close = t.count('<sc-if'), t.count('</sc-if>')
    div_delta = div_open - div_close
    scif_delta = scif_open - scif_close

    print(f"Template size: {len(t)} chars")
    print(f"<div>:   {div_open} open, {div_close} close  Δ={div_delta:+d}")
    print(f"<sc-if>: {scif_open} open, {scif_close} close  Δ={scif_delta:+d}")

    ok = True
    if div_delta != 0 or scif_delta != 0:
        ok = False
        print("\n*** STRUCTURAL IMBALANCE — template will break panel switching ***")

    # Per-panel depth trace: every MAIN panel must share one depth.
    print("\nDiv depth at each show* sc-if (main panels should all match):")
    depths = {}
    for m in re.finditer(r'<sc-if\s+value="\{\{\s*(show\w+)\s*\}\}"', t):
        name = m.group(1)
        pre = t[:m.start()]
        d = pre.count('<div') - pre.count('</div>')
        sd = pre.count('<sc-if') - pre.count('</sc-if>')
        depths.setdefault(name, (d, sd))
        print(f"  {name}: div_depth={d}, sc-if_depth={sd}")

    # showLogin (outer overlay) and showLogFilters (nested inside Logs) legitimately
    # differ; the MAIN panels are everything else.
    main = {k: v for k, v in depths.items()
            if k not in ('showLogin', 'showLogFilters')}
    if main:
        first_depth = next(iter(main.values()))[0]
        bad = [k for k, (d, _) in main.items() if d != first_depth]
        if bad:
            ok = False
            print(f"\n*** PANEL DEPTH MISMATCH — these are at the wrong depth: {bad}")
            print(f"    (expected div_depth={first_depth}; the bad patch is the panel "
                  f"swap JUST BEFORE the first mismatched panel)")

    # Per-patch NET delta — surfaces which patch introduced the imbalance.
    try:
        from _redesign_patches import _REDESIGN_PAIRS
        print("\nPer-patch NET div/sc-if delta (NEW delta minus OLD delta):")
        for i, (old, new) in enumerate(_REDESIGN_PAIRS):
            nd = (new.count('<div') - new.count('</div>')) - \
                 (old.count('<div') - old.count('</div>'))
            ns = (new.count('<sc-if') - new.count('</sc-if>')) - \
                 (old.count('<sc-if') - old.count('</sc-if>'))
            flag = "  <-- NONZERO" if (nd or ns) else ""
            print(f"  patch {i:2d}: div Δ={nd:+d}, sc-if Δ={ns:+d}{flag}")
    except Exception as e:
        print(f"\n(could not load _REDESIGN_PAIRS for per-patch delta: {e})")

    print("\n" + ("PASS — template structurally balanced." if ok
                  else "FAIL — fix the imbalance before restarting."))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
