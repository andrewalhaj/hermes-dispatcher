import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from routes.workspace import _jail  # jails to ~/workspace or ~/.hermes; finding #4

router = APIRouter()


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
    return FileResponse(str(resolved), media_type=mime or "application/octet-stream")
