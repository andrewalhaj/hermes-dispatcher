import sys, json, re
from playwright.sync_api import sync_playwright

URL = "http://100.64.150.51:7456"
SHOT = "/root/.hermes/image_cache/od_studio_authed.png"

# read token from the access reference file (never hardcode)
raw = open("/root/.hermes/references/open-design-access.txt").read()
m = re.search(r'[A-Za-z0-9_\-]{40,}', raw)
TOKEN = m.group(0) if m else ""

def main():
    if not TOKEN:
        print("NO TOKEN FOUND"); return
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-dev-shm-usage","--disable-gpu"],
        )
        # THIS is the Option A mechanism: inject Authorization on every request
        ctx = browser.new_context(
            viewport={"width":1440,"height":900},
            extra_http_headers={"Authorization": f"Bearer {TOKEN}"},
        )
        page = ctx.new_page()
        statuses=[]
        page.on("response", lambda r: statuses.append((r.status, r.url)) if "/api/" in r.url else None)
        page.goto(URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(6000)
        title = page.title()
        body_text = page.evaluate("()=>document.body?document.body.innerText.slice(0,600):'(no body)'")
        page.screenshot(path=SHOT, full_page=False)
        # summarize api call statuses
        codes={}
        for s,u in statuses: codes[s]=codes.get(s,0)+1
        print("TITLE:", title)
        print("API STATUS COUNTS:", json.dumps(codes))
        print("SAMPLE API CALLS:")
        for s,u in statuses[:8]:
            print(f"  {s}  {u.replace(URL,'')}")
        print("\nBODY TEXT (first 600):")
        print(body_text)
        print("\nSCREENSHOT:", SHOT)
        browser.close()

if __name__=="__main__":
    main()
