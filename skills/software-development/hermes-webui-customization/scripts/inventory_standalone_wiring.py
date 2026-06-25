"""Inventory a Hermes standalone WebUI: which data is WIRED vs still MOCK.

Run with the hermes-agent venv from the served project dir, e.g.:
    cd /root/projects/hermes-webui-new && \
    HERMES_HOME=/root/.hermes /usr/local/lib/hermes-agent/venv/bin/python \
    <this-script>

Prints, in one pass:
  - the panel set (s.panel === 'X'), the show* renderVals keys, and any
    show* hardwired to a literal bool (DEAD PANELS — the #1 populate gap)
  - the rail*/nav* keys + railOf/navOf ids (so you know a panel is REACHABLE
    once you flip its show gate)
  - UPPER-CASE class-field mock arrays/objects (candidate gaps)
  - __RD_ referenced in the RAW standalone vs AFTER _patch_standalone vs what
    _build_global_data() actually injects (the three lists should reconcile;
    a __RD_ in _build_global_data but NOT in the patched js is consumed by a
    dc-import sub-component as a window global, not the main component)
  - mock arrays STILL hardcoded after the patch (the true remaining gaps;
    static UI scaffolding like COMMANDS/TABS will show here too — those are
    NOT gaps, confirm by reading their usage)
  - SECOND-ORDER GAPS (the populate-phase blind spot, added 2026-06-19): values
    HARDCODED INSIDE already-wired renderVals blocks. The UPPER-CASE-mock scan
    above MISSES these because they're lowercase keys with literal string/number
    values — e.g. `agentSummary = [{value:'5',...}]`, `{ label:'3 ready' }`,
    `tokInPct: '63%'`, `val: '7', lbl: 'Day Streak'`, and a `profiles: [{...mock}]`
    array. A panel can read a real `__RD_*` global for SOME fields and still show
    fabricated constants for others. Grep the patched JS for suspicious literals
    and reconcile each against a real builder before declaring "fully wired."

Adjust the two paths below if the served dir differs (read it fresh from the
live systemd unit's WorkingDirectory — never assume).
"""
import re, json, sys

PROJECT = "/root/projects/hermes-webui-new"
STANDALONE = f"{PROJECT}/standalone.html"
sys.path.insert(0, "/usr/local/lib/hermes-agent")
sys.path.insert(0, PROJECT)

OPEN_TAG = '<script type="__bundler/template">'


def extract_component_js(raw: str) -> tuple[str, str]:
    """Return (template_str, component_js). Byte-walks the JSON-encoded
    __bundler/template string (regex on </script> truncates it)."""
    pos = raw.find(OPEN_TAG)
    i = pos + len(OPEN_TAG)
    while raw[i] in " \t\n\r":
        i += 1
    j = i + 1
    while j < len(raw):
        ch = raw[j]
        if ch == "\\":
            j += 2
            continue
        if ch == '"':
            j += 1
            break
        j += 1
    tpl = json.loads(raw[i:j])
    scripts = list(re.finditer(r"<script[^>]*>(.*?)</script>", tpl, re.DOTALL))
    return tpl, scripts[-1].group(1)  # component class = LAST script


def main():
    raw = open(STANDALONE).read()
    tpl, js = extract_component_js(raw)
    print("=== component JS chars:", len(js))

    print("\n=== PANELS (s.panel === 'X'):",
          sorted(set(re.findall(r"s\.panel\s*===\s*'([a-zA-Z]+)'", js))))
    print("=== show* keys:",
          sorted(set(re.findall(r"(show[A-Z][a-zA-Z]+)\s*:", js))))
    print("=== show* hardwired to literal bool (DEAD PANELS):",
          re.findall(r"(show[A-Z][a-zA-Z]+)\s*:\s*(false|true)\b", js))
    print("=== railOf ids:", sorted(set(re.findall(r"railOf\('([a-z]+)'\)", js))))
    print("=== navOf ids:", sorted(set(re.findall(r"navOf\('([a-z]+)'\)", js))))

    print("\n=== UPPER-CASE class-field mock arrays:",
          sorted(set(re.findall(r"\n\s+([A-Z][A-Z0-9_]{2,})\s*=\s*\[", js))))
    print("=== UPPER-CASE class-field mock objects:",
          sorted(set(re.findall(r"\n\s+([A-Z][A-Z0-9_]{2,})\s*=\s*\{", js))))

    rd_raw = sorted(set(re.findall(r"window\.__RD_([A-Z_]+)__", js)))
    print("\n=== __RD_ in RAW standalone:", rd_raw)

    import server  # noqa: E402  (needs PROJECT on sys.path + HERMES_HOME env)
    patched = server._patch_standalone(raw)
    _, pjs = extract_component_js(patched)
    rd_after = sorted(set(re.findall(r"window\.__RD_([A-Z_]+)__", pjs)))
    print("=== __RD_ wired AFTER _patch_standalone:", rd_after)

    gd = server._build_global_data()
    injected = sorted(k.replace("__RD_", "").replace("__", "") for k in gd)
    print("=== __RD_ injected by _build_global_data:", injected)
    print("=== injected but NOT in patched js (dc-import / window-global only):",
          sorted(set(injected) - set(rd_after)))

    print("\n=== mock arrays STILL hardcoded after patch (gaps + scaffolding):",
          sorted(set(re.findall(r"\n\s+([A-Z][A-Z0-9_]{2,})\s*=\s*\[", pjs))))

    # ── SECOND-ORDER GAPS: hardcoded literals inside already-wired blocks ──────
    # These are the populate-phase blind spot. Heuristic flags — each is a
    # CANDIDATE, confirm by reading the block (some literals are legit static
    # scaffolding like icon paths or color stops). Run against the PATCHED js so
    # you only see what survives to the browser.
    print("\n=== SECOND-ORDER candidates (hardcoded values in wired blocks) ===")
    # lowercase renderVals arrays of objects (e.g. profiles:, models:, skills:)
    low_arrays = sorted(set(re.findall(r"\n\s+([a-z][a-zA-Z0-9_]+)\s*:\s*\[\s*\{", pjs)))
    print("  lowercase `key: [{...}]` arrays (mock-prone):", low_arrays)
    # short quoted-number+unit strings often = fake stats ('3 ready', '95%', '6.1M')
    suspicious = sorted(set(re.findall(
        r"'(\d+(?:\.\d+)?\s*(?:ready|blocked|running|idle)|\d+%|\d+(?:\.\d+)?[MmKk])'", pjs)))
    print("  suspicious stat literals:", suspicious[:40])
    # synthetic data tells: Math.sin/Math.random in a *_for_ui-shaped block
    if re.search(r"(heatRows|spark|series|sysData)\s*=.*Math\.(sin|random)", pjs, re.DOTALL):
        print("  WARNING: Math.sin/Math.random synthetic series present "
              "(heatmap/sparkline/metrics may be fabricated, not from a builder)")


if __name__ == "__main__":
    main()
