import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

_ALLOWED_ROOTS = [
    os.path.realpath("/root/workspace"),
    os.path.realpath(os.path.expanduser("~/.hermes")),
]

MAX_READ_BYTES = 100 * 1024
BINARY_PROBE_BYTES = 8 * 1024


def _jail(path: str) -> Path:
    real = os.path.realpath(path)
    if not any(real == r or real.startswith(r + os.sep) for r in _ALLOWED_ROOTS):
        raise HTTPException(status_code=403, detail="Access denied")
    p = Path(real)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    return p


@router.get("/workspace/ls")
async def workspace_ls(path: str = "/root/workspace") -> list[dict]:
    p = _jail(path)
    if not p.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")

    entries: list[dict] = []
    try:
        children = list(p.iterdir())
    except OSError:
        return []

    children.sort(key=lambda c: (not c.is_dir(), c.name.lower()))

    for child in children:
        try:
            st = child.stat()
            entries.append(
                {
                    "name": child.name,
                    "type": "dir" if child.is_dir() else "file",
                    "size": 0 if child.is_dir() else st.st_size,
                    "modified": int(st.st_mtime),
                }
            )
        except OSError:
            continue

    return entries


@router.get("/workspace/read")
async def workspace_read(path: str) -> dict:
    p = _jail(path)
    if not p.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    size = p.stat().st_size

    with p.open("rb") as fh:
        probe = fh.read(BINARY_PROBE_BYTES)
        if b"\x00" in probe:
            raise HTTPException(status_code=415, detail="binary file")
        fh.seek(0)
        raw = fh.read(MAX_READ_BYTES)

    return {
        "path": str(p),
        "content": raw.decode("utf-8", errors="replace"),
        "size": size,
        "truncated": size > MAX_READ_BYTES,
    }
