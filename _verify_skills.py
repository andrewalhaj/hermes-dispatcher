import sys, json, urllib.request, urllib.error, subprocess, time, os, signal

BASE = "http://localhost:8000"

def get(path):
    with urllib.request.urlopen(BASE + path, timeout=10) as r:
        return r.status, r.read().decode()

def req(path, method, data=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(BASE + path, data=body, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

# health
print("HEALTH:", get("/api/health"))

# list
st, txt = get("/api/skills")
data = json.loads(txt)
print("LIST status:", st, "COUNT:", len(data))
sample = data[0]
print("SAMPLE:", json.dumps(sample))
sid = sample["id"]

# get one
st, txt = get("/api/skills/" + sid)
d = json.loads(txt)
print("GET", sid, "status:", st, "content_len:", len(d["content"]), "starts:", repr(d["content"][:40]))

# PUT no-op
orig = d["content"]
st, txt = req("/api/skills/" + sid, "PUT", {"content": orig})
print("PUT noop:", st, txt)
st2, txt2 = get("/api/skills/" + sid)
print("PUT roundtrip unchanged:", json.loads(txt2)["content"] == orig)

# POST throwaway
st, txt = req("/api/skills", "POST", {"category": "_tmp_test", "name": "_tmp_probe",
                                      "content": "---\nname: _tmp_probe\ndescription: probe\n---\nbody\n"})
print("POST:", st, txt)
# confirm listed
st, txt = get("/api/skills/_tmp_probe")
print("GET probe:", st, json.loads(txt)["name"] if st == 200 else txt)
# DELETE
st, txt = req("/api/skills/_tmp_probe", "DELETE")
print("DELETE:", st, txt)
# confirm gone
st, txt = get("/api/skills/_tmp_probe")
print("GET probe after delete (expect 404):", st)
print("dir _tmp_test exists:", os.path.exists(os.path.expanduser("~/.hermes/skills/_tmp_test")))
