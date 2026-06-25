#!/usr/bin/env python3
"""Prove the Option-A fix end-to-end: inject Authorization: Bearer *** on every
request (exactly what a ModHeader rule does in the user's browser), load the OD
studio over its tailnet IP, and confirm /api/* flips from 401 -> 200 and the
runtime picker renders (no more "no agent").

Run with the Hermes venv python so playwright is importable, e.g.:
    /usr/local/lib/hermes-agent/venv/bin/python <this-script>
or  cd /root && source .venv/bin/activate && python <this-script>

PITFALLS baked in:
- wait_until='networkidle' NEVER fires (studio holds an open WS/long-poll) ->
  use 'domcontentloaded' + a fixed settle wait.
- token is read from the access reference file, never hardcoded.
- header injection is via browser.new_context(extra_http_headers=...), which is
  the in-browser equivalent of the ModHeader rule we hand the user.
"""
import json, re
from playwright.sync_api import sync_playwright

URL = "http://100.64.150.51:7456"            # OD studio tailnet origin (adjust per host)
TOKEN_FILE = "/root/.hermes/references/open-design-access.txt"
SHOT = "/root/.hermes/image_cache/od_studio_authed.png"

raw = open(TOKEN_FILE).read()
m = re.search(r"[A-Za-z0-9_\-]{40,}", raw)   # OD_API_TOKEN is a 64-char hex string
TOKEN = m.group(0) if m else ""


def main():
    if not TOKEN:
        print("NO TOKEN FOUND in", TOKEN_FILE)
        return
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        # THIS is the Option-A mechanism (ModHeader equivalent): attach the
        # bearer on EVERY request. The daemon's /api gate reads it off the
        # socket request, not localStorage.
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            extra_http_headers={"Authorization": f"Bearer {TOKEN}"},
        )
        page = ctx.new_page()
        statuses = []
        page.on("response",
                lambda r: statuses.append((r.status, r.url)) if "/api/" in r.url else None)
        page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(6000)  # let the SPA fire its /api/* calls
        title = page.title()
        body = page.evaluate("()=>document.body?document.body.innerText.slice(0,600):'(no body)'")
        page.screenshot(path=SHOT, full_page=False)
        codes = {}
        for s, _ in statuses:
            codes[s] = codes.get(s, 0) + 1
        print("TITLE:", title)
        print("API STATUS COUNTS:", json.dumps(codes))  # expect mostly 200; all-401 == fix failed
        print("BODY (first 600):")
        print(body)
        print("SCREENSHOT:", SHOT)
        browser.close()


if __name__ == "__main__":
    main()
