import mimetypes
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

router = APIRouter(prefix="/chat")

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/root/.hermes"))
IMAGE_CACHE = HERMES_HOME / "image_cache"
DOC_CACHE = HERMES_HOME / "cache" / "documents"


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
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
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

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
