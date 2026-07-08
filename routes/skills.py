import os
import re
import shutil
from pathlib import Path
from typing import Any
from datetime import datetime

import yaml
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

SKILLS_ROOT = Path(os.path.expanduser("~/.hermes/skills"))
CONFIG_PATH = Path(os.path.expanduser("~/.hermes/config.yaml"))


def _parse_frontmatter(text: str) -> dict:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}
    try:
        return yaml.safe_load(match.group(1)) or {}
    except Exception:
        return {}


def _load_disabled_skills(platform: str | None = None) -> set[str]:
    """Load the set of disabled skill ids from config.yaml.

    Merges the global ``skills.disabled`` list with the platform-specific
    ``skills.platform_disabled.<platform>`` list when ``platform`` is given.
    """
    if not CONFIG_PATH.exists():
        return set()
    try:
        config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        if not config:
            return set()
        sk = config.get("skills", {}) or {}
        disabled = set(sk.get("disabled", []) or [])
        if platform:
            plat = sk.get("platform_disabled", {}) or {}
            disabled |= set(plat.get(platform, []) or [])
        return disabled
    except Exception:
        return set()


def _set_disabled_skills(disabled_ids: set[str]) -> None:
    """Update config.yaml with the new set of disabled skill ids."""
    if not CONFIG_PATH.exists():
        return
    try:
        config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        if config is None:
            config = {}
        if "skills" not in config:
            config["skills"] = {}
        config["skills"]["disabled"] = sorted(list(disabled_ids))
        CONFIG_PATH.write_text(yaml.dump(config, default_flow_style=False), encoding="utf-8")
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update config.yaml")


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


def _skill_entry(skill_md: Path, disabled_ids: set[str]) -> dict[str, Any]:
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fm = _parse_frontmatter(text)

    skill_dir = skill_md.parent
    parent_dir = skill_dir.parent
    category = parent_dir.name if parent_dir != SKILLS_ROOT else "uncategorized"
    skill_id = skill_dir.name

    tags: list[str] = []
    if isinstance(fm.get("tags"), list):
        tags = fm["tags"]
    else:
        try:
            hermes_meta = fm.get("metadata", {}).get("hermes", {})
            tags = hermes_meta.get("tags", []) or []
        except Exception:
            tags = []

    # Get last modified time
    try:
        mtime = skill_md.stat().st_mtime
        last_modified = datetime.fromtimestamp(mtime).isoformat()
    except Exception:
        last_modified = None

    return {
        "id": skill_id,
        "name": fm.get("name") or skill_dir.name,
        "description": str(fm.get("description") or ""),
        "category": category,
        "tags": [str(t) for t in tags],
        "path": str(skill_md),
        "enabled": skill_id not in disabled_ids,
        "version": str(fm.get("version") or "1.0.0"),
        "author": str(fm.get("author") or ""),
        "last_modified": last_modified,
    }


@router.get("/skills")
async def list_skills(platform: str = Query(default="telegram")) -> list[dict]:
    index = _build_index()
    disabled_ids = _load_disabled_skills(platform=platform)
    results = []
    for skill_id, skill_md in index.items():
        try:
            results.append(_skill_entry(skill_md, disabled_ids))
        except Exception:
            results.append({
                "id": skill_id,
                "name": skill_id,
                "description": "",
                "category": "uncategorized",
                "tags": [],
                "path": str(skill_md),
                "enabled": skill_id not in disabled_ids,
                "version": "1.0.0",
                "author": "",
                "last_modified": None,
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
    disabled_ids = _load_disabled_skills()
    return {
        "id": id,
        "name": str(fm.get("name") or id),
        "category": category,
        "path": str(skill_md),
        "content": text,
        "enabled": id not in disabled_ids,
        "version": str(fm.get("version") or "1.0.0"),
        "author": str(fm.get("author") or ""),
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


class ToggleBody(BaseModel):
    enabled: bool


@router.put("/skills/{id}/enabled")
async def toggle_skill(id: str, body: ToggleBody, platform: str = Query(default="telegram")) -> dict:
    """Enable or disable a skill by updating config.yaml.

    When ``platform`` is set (default ``telegram``), the toggle writes to
    ``skills.platform_disabled.<platform>``. Pass an empty ``platform`` to
    toggle the global ``skills.disabled`` list instead.
    """
    index = _build_index()
    if id not in index:
        raise HTTPException(status_code=404, detail="Skill not found")

    if not platform:
        # Global toggle
        disabled_ids = _load_disabled_skills()
        if body.enabled:
            disabled_ids.discard(id)
        else:
            disabled_ids.add(id)
        _set_disabled_skills(disabled_ids)
    else:
        # Platform-specific toggle
        try:
            config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
            sk = config.setdefault("skills", {})
            plat_disabled = sk.setdefault("platform_disabled", {})
            plat_list = set(plat_disabled.get(platform, []) or [])
            if body.enabled:
                plat_list.discard(id)
            else:
                plat_list.add(id)
            plat_disabled[platform] = sorted(list(plat_list))
            CONFIG_PATH.write_text(yaml.dump(config, default_flow_style=False), encoding="utf-8")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to update config.yaml")

    return {"ok": True, "enabled": body.enabled}


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
