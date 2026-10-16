import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

_INLINE_IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp", "image/avif"}

# Path jail (audit finding #4). Moved here from the deleted routes/workspace.py.
_ALLOWED_ROOTS = [
    os.path.realpath(os.path.expanduser("~/workspace")),
    os.path.realpath(os.path.expanduser("~/.hermes")),
]


def _jail(path: str) -> Path:
    """Resolve *path* and refuse anything outside _ALLOWED_ROOTS (403) or missing (404)."""
    real = os.path.realpath(path)
    if not any(real == r or real.startswith(r + os.sep) for r in _ALLOWED_ROOTS):
        raise HTTPException(status_code=403, detail="Access denied")
    p = Path(real)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Path not found")
    return p


@router.get("/media")
async def serve_media(path: str = "") -> FileResponse:
    if not path:
        raise HTTPException(status_code=400, detail="path is required")
    # Refuse dotfiles (e.g. .env, .dashboard_passwd_hash)
    if Path(path).name.startswith("."):
        raise HTTPException(status_code=400, detail="invalid path")
    resolved = _jail(path)  # raises 403 if outside allowed roots, 404 if missing
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="not found")
    mime, _ = mimetypes.guess_type(str(resolved))
    mime = mime or "application/octet-stream"
    # Audit #13: the extension comes from the client's file name. An .html/.svg
    # served inline from the dashboard origin would run script with the session
    # cookie. Only plain raster images are rendered inline; everything else is
    # a download, and nosniff stops the browser second-guessing the type.
    inline = mime in _INLINE_IMAGE_TYPES
    headers = {"X-Content-Type-Options": "nosniff"}
    if not inline:
        headers["Content-Disposition"] = f'attachment; filename="{resolved.name}"'
        if mime.startswith(("text/", "image/svg", "application/xhtml")):
            mime = "application/octet-stream"
    return FileResponse(str(resolved), media_type=mime, headers=headers)
