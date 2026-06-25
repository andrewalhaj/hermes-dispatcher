import subprocess, sys, time, json, urllib.request, urllib.error, signal, os

# 1. import check
r = subprocess.run([".venv/bin/python","-c","import routes.memory; print('import OK')"],
                   capture_output=True, text=True, cwd="/root/hermes-dispatcher")
print("IMPORT:", r.stdout.strip(), r.stderr.strip()[-300:])

# 2. start server
PORT=8911
srv = subprocess.Popen([".venv/bin/python","-m","uvicorn","routes.memory:app","--port",str(PORT)],
                       cwd="/root/hermes-dispatcher",
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4)
def get(path, method="GET", body=None):
    url=f"http://localhost:{PORT}"+path
    data=json.dumps(body).encode() if body else None
    req=urllib.request.Request(url, data=data, method=method,
                               headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())
try:
    files=get("/api/memory/files")
    print("FILES keys:", sorted(files.keys()), "mem_chars",files.get("memory_chars"),
          "user_chars",files.get("user_chars"),"caps",files.get("memory_cap"),files.get("user_cap"))
    gal=get("/api/memory/galaxy")
    tiers={}
    for n in gal["nodes"]:
        tiers[n["tier"]]=tiers.get(n["tier"],0)+1
    print("GALAXY nodes:",len(gal["nodes"]),"by tier:",tiers,"edges:",len(gal.get("edges",[])))
    print("SAMPLE node:", json.dumps(gal["nodes"][0]) if gal["nodes"] else "none")
    # PUT round trip (write back the same content -> no data loss)
    orig=files["memory"]
    put=get("/api/memory/files",method="PUT",body={"file":"memory","content":orig})
    print("PUT memory:", put)
    bad=False
    try:
        get("/api/memory/files",method="PUT",body={"file":"bogus","content":"x"})
    except urllib.error.HTTPError as e:
        bad=(e.code==400)
    print("PUT bad file rejected with 400:", bad)
finally:
    srv.terminate()
    try: srv.wait(timeout=5)
    except: srv.kill()
