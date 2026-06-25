import server
app = server.app
# collect all route paths recursively
paths = set()
def walk(routes):
    for r in routes:
        p = getattr(r, "path", None)
        if p: paths.add(p)
        for sub in (getattr(r, "routes", None) or []):
            walk([sub])
walk(app.routes)
print("FULL APP IMPORT OK")
print("media route registered:", "/api/media" in paths)
# media handler still works
import asyncio, tempfile, os
from routes.media import serve_media
from fastapi import HTTPException
async def t():
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"\x00\x00\x00\x18ftypmp42"); tmp=f.name
    r = await serve_media(path=tmp)
    print("media mp4:", r.status_code, r.media_type)
    os.unlink(tmp)
    try:
        await serve_media(path="../x")
    except HTTPException as e:
        print("traversal guard:", e.status_code)
asyncio.run(t())
