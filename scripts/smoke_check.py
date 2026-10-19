#!/usr/bin/env python3
"""Post-deploy smoke check: health, bundle hash, and headless browser render.

Usage: python3 scripts/smoke_check.py [BASE_URL]
Default base URL: http://127.0.0.1:8787

Exits non-zero with a descriptive message on any failure.
Run from the repository root so app/dist/assets is resolvable.
"""
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8787"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def check(label: str, ok: bool, detail: str = "") -> None:
    status = "OK  " if ok else "FAIL"
    print(f"[{status}] {label}" + (f": {detail}" if detail else ""))
    if not ok:
        fail(f"{label} — {detail}")


# 1. Health
try:
    resp = urllib.request.urlopen(f"{BASE_URL}/api/health", timeout=10)
    check("/api/health == 200", resp.status == 200, f"got {resp.status}")
except Exception as e:
    fail(f"/api/health request failed: {e}")

# 2. Extract served bundle filename from index HTML
html = ""
try:
    resp2 = urllib.request.urlopen(BASE_URL + "/", timeout=10)
    html = resp2.read().decode()
except Exception as e:
    fail(f"GET / failed: {e}")

m = re.search(r'/assets/(index-[^"\']+\.js)', html)
check("index HTML contains /assets/index-*.js", bool(m))
assert m  # guaranteed by check() above
served_name = m.group(1)
print(f"       served bundle: {served_name}")

# 3. Dist file must match
dist_dir = Path("app/dist/assets")
if not dist_dir.exists():
    fail("app/dist/assets not found (run from repo root)")
dist_bundles = list(dist_dir.glob("index-*.js"))
check("dist/assets has exactly one index-*.js", len(dist_bundles) == 1, str(dist_bundles))
dist_name = dist_bundles[0].name
check("served bundle matches dist", served_name == dist_name, f"{served_name} vs {dist_name}")

# 4. Bundle fetchable
try:
    resp3 = urllib.request.urlopen(f"{BASE_URL}/assets/{served_name}", timeout=15)
    check(f"/assets/{served_name} == 200", resp3.status == 200, f"got {resp3.status}")
except Exception as e:
    fail(f"bundle fetch failed: {e}")

# 5. Headless browser: root must render
browser = shutil.which("chromium-browser") or shutil.which("chromium") or shutil.which("google-chrome")
if not browser:
    fail("no chromium/chrome found; install chromium-browser")

dom = ""
try:
    result = subprocess.run(
        [browser, "--headless=new", "--no-sandbox", "--disable-gpu",
         "--virtual-time-budget=8000", "--dump-dom", BASE_URL + "/"],
        capture_output=True, text=True, timeout=30,
    )
    dom = result.stdout
except subprocess.TimeoutExpired:
    fail("headless browser timed out after 30 s")

# Root must exist and have children (non-whitespace content after the opening tag)
m2 = re.search(r'<div id="root"[^>]*>([\s\S]*?)</div>', dom)
if not m2:
    fail('<div id="root"> not found in DOM dump')
root_content = m2.group(1).strip()
check('<div id="root"> has rendered content', bool(root_content),
      "(empty — JS may have crashed on load)")

print("\nAll checks passed.")
