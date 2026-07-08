import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/media")
async def serve_media(path: str = "") -> FileResponse:
    if not path:
        raise HTTPException(status_code=400, detail="path is required")
    if ".." in path:
        raise HTTPException(status_code=400, detail="invalid path")
    resolved = Path(path).resolve()
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="not found")
    mime, _ = mimetypes.guess_type(str(resolved))
    return FileResponse(str(resolved), media_type=mime or "application/octet-stream")
