import os
import re
import shutil
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

SKILLS_ROOT = Path(os.path.expanduser("~/.hermes/skills"))


def _parse_frontmatter(text: str) -> dict:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except Exception:
        return {}


def _build_index() -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not SKILLS_ROOT.exists():
        return index
    for skill_md in SKILLS_ROOT.rglob("SKILL.md"):
        index[skill_md.parent.name] = skill_md
    return index


def _guard_path(path: Path) -> None:
    try:
        path.resolve().relative_to(SKILLS_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Path traversal detected")


def _skill_entry(skill_md: Path) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fm = _parse_frontmatter(text)

    skill_dir = skill_md.parent
    parent_dir = skill_dir.parent
    category = parent_dir.name if parent_dir != SKILLS_ROOT else "uncategorized"

    tags: list[str] = []
    if isinstance(fm.get("tags"), list):
        tags = fm["tags"]
    else:
        try:
            hermes_meta = fm.get("metadata", {}).get("hermes", {})
            tags = hermes_meta.get("tags", []) or []
        except Exception:
            tags = []

    return {
        "id": skill_dir.name,
        "name": fm.get("name") or skill_dir.name,
        "description": str(fm.get("description") or ""),
        "category": category,
        "tags": [str(t) for t in tags],
        "path": str(skill_md),
    }


@router.get("/skills")
async def list_skills() -> list[dict]:
    index = _build_index()
    results = []
    for skill_id, skill_md in index.items():
        try:
            results.append(_skill_entry(skill_md))
        except Exception:
            results.append({
                "id": skill_id,
                "name": skill_id,
                "description": "",
                "category": "uncategorized",
                "tags": [],
                "path": str(skill_md),
            })
    return results


@router.get("/skills/{id}")
async def get_skill(id: str) -> dict:
    index = _build_index()
    if id not in index:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill_md = index[id]
    _guard_path(skill_md)
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fm = _parse_frontmatter(text)
    skill_dir = skill_md.parent
    parent_dir = skill_dir.parent
    category = parent_dir.name if parent_dir != SKILLS_ROOT else "uncategorized"
    return {
        "id": id,
        "name": str(fm.get("name") or id),
        "category": category,
        "path": str(skill_md),
        "content": text,
    }


class PutBody(BaseModel):
    content: str


@router.put("/skills/{id}")
async def update_skill(id: str, body: PutBody) -> dict:
    index = _build_index()
    if id not in index:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill_md = index[id]
    _guard_path(skill_md)
    skill_md.write_text(body.content, encoding="utf-8")
    return {"ok": True}


class PostBody(BaseModel):
    name: str
    category: str
    content: str


@router.post("/skills")
async def create_skill(body: PostBody) -> dict:
    skill_dir = SKILLS_ROOT / body.category / body.name
    _guard_path(skill_dir)
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        raise HTTPException(status_code=400, detail="Skill already exists")
    skill_dir.mkdir(parents=True, exist_ok=False)
    skill_md.write_text(body.content, encoding="utf-8")
    return {"ok": True, "id": body.name, "path": str(skill_md)}


@router.delete("/skills/{id}")
async def delete_skill(id: str) -> dict:
    index = _build_index()
    if id not in index:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill_md = index[id]
    skill_dir = skill_md.parent
    _guard_path(skill_dir)
    parent_dir = skill_dir.parent
    shutil.rmtree(skill_dir)
    # Remove parent category dir if now empty and within skills root
    if parent_dir != SKILLS_ROOT and parent_dir.is_dir() and not any(parent_dir.iterdir()):
        try:
            parent_dir.rmdir()
        except Exception:
            pass
    return {"ok": True}
