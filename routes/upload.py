import mimetypes
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.routing import APIRoute

HERMES_HOME = Path(os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes")))
IMAGE_CACHE = HERMES_HOME / "image_cache"
DOC_CACHE = HERMES_HOME / "cache" / "documents"
# Audit #13: copyfileobj had no limit — one upload could fill the disk.
MAX_UPLOAD_BYTES = int(os.environ.get("DASHBOARD_MAX_UPLOAD_MB", "25")) * 1024 * 1024
_MULTIPART_SLACK = 64 * 1024  # boundaries + part headers around the file


class _ContentLengthCap(APIRoute):
    """413 on Content-Length before FastAPI parses the body: parsing spools the
    whole upload to a temp file first, so the copy cap alone can't save the disk."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def capped(request):
            if int(request.headers.get("content-length") or 0) > MAX_UPLOAD_BYTES + _MULTIPART_SLACK:
                raise HTTPException(status_code=413, detail=f"file exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
            return await handler(request)

        return capped


# shortcut: chunked bodies (no Content-Length) still spool in full before _copy_limited;
# upgrade to a streaming ASGI body cap if anything but the dashboard ever posts here.
router = APIRouter(prefix="/chat", route_class=_ContentLengthCap)


def _copy_limited(src, dst, limit: int) -> int:
    """Copy src→dst, raising 413 once more than *limit* bytes have been read."""
    total = 0
    while True:
        chunk = src.read(1024 * 1024)
        if not chunk:
            return total
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=f"file exceeds {limit // (1024 * 1024)} MB limit")
        dst.write(chunk)


# sync def: FastAPI runs it in a thread, so the 25 MB copy doesn't block the event loop.
@router.post("/upload")
def upload_file(file: UploadFile = File(...)):
    IMAGE_CACHE.mkdir(parents=True, exist_ok=True)
    DOC_CACHE.mkdir(parents=True, exist_ok=True)

    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    is_image = mime.startswith("image/")
    is_text = mime.startswith("text/")

    ext = Path(file.filename or "upload").suffix or (".png" if is_image else ".bin")
    uid = uuid.uuid4().hex[:12]
    safe_name = f"webui_{uid}{ext}"

    dest_dir = IMAGE_CACHE if is_image else DOC_CACHE
    dest = dest_dir / safe_name
    try:
        with dest.open("wb") as f:
            _copy_limited(file.file, f, MAX_UPLOAD_BYTES)
    except HTTPException:
        dest.unlink(missing_ok=True)  # don't leave the partial file behind
        raise

    content = None
    if is_text:
        try:
            content = dest.read_text(errors="replace")[:40_000]
        except Exception:
            content = None

    return {
        "path": str(dest),
        "filename": file.filename or safe_name,
        "mime": mime,
        "is_image": is_image,
        "is_text": is_text,
        "text_content": content,
    }
