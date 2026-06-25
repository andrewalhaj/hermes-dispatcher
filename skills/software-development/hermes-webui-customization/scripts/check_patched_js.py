#!/usr/bin/env python3
"""Verify a patched-standalone WebUI: node --check the EXTRACTED patched
component JS before any gated restart.

Catches the two populate-phase syntax traps (mid-expression _replace_block end
marker; any js.replace that produces valid-Python-but-invalid-JS) that the
server-side `_build_global_data()` build does NOT catch. See
references/populate-data-verify-gate.md.

Run from the served dir with the hermes-agent venv:
    cd /root/projects/hermes-webui-new && \
    HERMES_HOME=/root/.hermes /usr/local/lib/hermes-agent/venv/bin/python \
    <skill>/scripts/check_patched_js.py

Exit 0 + "node --check: PASS" = safe to restart. FAIL prints node's error with
the line number in the decoded component JS (maps to your patch region).

Adjust PROJECT if the live unit's WorkingDirectory differs (read it fresh from
`systemctl cat hermes-webui` — never assume).
"""
import re, json, sys, os, subprocess, tempfile

PROJECT = os.environ.get("WEBUI_PROJECT", "/root/projects/hermes-webui-new")
STANDALONE = f"{PROJECT}/standalone.html"
sys.path.insert(0, "/usr/local/lib/hermes-agent")
sys.path.insert(0, PROJECT)
os.environ.setdefault("HERMES_HOME", "/root/.hermes")

OPEN_TAG = '<script type="__bundler/template">'


def extract_component_js(html: str) -> str:
    """Byte-walk the JSON-encoded __bundler/template string (regex on
    </script> truncates it), return the LAST <script> block (component class)."""
    pos = html.find(OPEN_TAG)
    if pos < 0:
        raise RuntimeError("__bundler/template not found")
    i = pos + len(OPEN_TAG)
    while html[i] in " \t\n\r":
        i += 1
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
    tpl = json.loads(html[i:j])
    scripts = list(re.finditer(r"<script[^>]*>(.*?)</script>", tpl, re.DOTALL))
    return scripts[-1].group(1)


def main():
    import server  # needs PROJECT on sys.path + HERMES_HOME env

    # 1) builders run + dict assembles (necessary but NOT sufficient)
    d = server._build_global_data()
    print("build OK, __RD_ keys:", len(d))

    # 2) the real gate — patch, extract, node --check
    raw = open(STANDALONE).read()
    patched = server._patch_standalone(raw)
    pjs = extract_component_js(patched)

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(pjs)
        fname = f.name
    try:
        r = subprocess.run(["node", "--check", fname], capture_output=True, text=True)
    finally:
        os.unlink(fname)

    if r.returncode == 0:
        print("node --check: PASS — safe to restart")
        return 0
    print("node --check: FAIL")
    print(r.stderr.strip()[:800])
    print("\n^ line number is in the DECODED component JS — find that region in "
          "your _patch_standalone replacement and fix the marker.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
