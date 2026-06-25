import json
from routes import memory as m
files = m.get_files()
print("get_files: memory_chars", files["memory_chars"], "user_chars", files["user_chars"],
      "caps", files["memory_cap"], files["user_cap"])
gal = m.get_galaxy()
from collections import Counter
c = Counter(n["tier"] for n in gal["nodes"])
print("get_galaxy nodes:", len(gal["nodes"]), "by tier:", dict(c), "edges:", len(gal["edges"]))
for n in gal["nodes"][:4]:
    print("  node", n["id"], "tier", n["tier"], "label:", repr(n["label"]))
# bad-file rejection (call put with invalid file -> expect HTTPException)
from fastapi import HTTPException
try:
    m.put_files(m.PutFilesBody(file="bogus", content="x"))
    print("BAD-FILE: NOT rejected (FAIL)")
except HTTPException as e:
    print("BAD-FILE rejected:", e.status_code)
