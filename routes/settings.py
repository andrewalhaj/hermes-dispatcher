import os
import shutil
from pathlib import Path

import yaml
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

HERMES_HOME = os.environ.get("HERMES_HOME", "/root/.hermes")

_TOGGLE_KEYS = {
    "setStream", "setEndless", "setAutoApprove", "setNotify",
    "setUpdates", "setInsights", "setRedact", "setCliSessions",
}


def _config_path() -> Path:
    return Path(HERMES_HOME) / "config.yaml"


def _load_config() -> dict:
    p = _config_path()
    if not p.exists():
        return {}
    with open(p, "r") as f:
        return yaml.safe_load(f) or {}


def _dump_config(cfg: dict) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    bak = Path(str(p) + ".bak")
    if p.exists():
        shutil.copy2(p, bak)
    with open(p, "w") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, default_flow_style=False)


@router.get("/settings")
async def get_settings():
    cfg = _load_config()
    model = cfg.get("model") or {}
    display = cfg.get("display") or {}
    memory = cfg.get("memory") or {}
    agent = cfg.get("agent") or {}
    delegation = cfg.get("delegation") or {}
    dashboard = cfg.get("dashboard") or {}
    return {
        "model": {
            "default": model.get("default"),
            "provider": model.get("provider"),
        },
        "display": {
            "language": display.get("language"),
            "show_cost": display.get("show_cost"),
            "streaming": display.get("streaming"),
            "theme": display.get("theme"),
        },
        "memory": {
            "memory_char_limit": memory.get("memory_char_limit"),
            "user_char_limit": memory.get("user_char_limit"),
        },
        "reasoning_effort": agent.get("reasoning_effort"),
        "delegation": {
            "provider": delegation.get("provider"),
            "model": delegation.get("model"),
        },
        "agent": {
            "name": agent.get("name"),
            "workspace": agent.get("workspace"),
        },
        "dashboard": {k: dashboard[k] for k in _TOGGLE_KEYS if k in dashboard},
    }


@router.put("/settings")
async def put_settings(body: dict):
    try:
        cfg = _load_config()

        def _set(keys: list, value):
            if value is None:
                return
            node = cfg
            for k in keys[:-1]:
                node = node.setdefault(k, {})
            node[keys[-1]] = value

        bm = (body.get("model") or {})
        _set(["model", "default"], bm.get("default"))
        _set(["model", "provider"], bm.get("provider"))

        bd = (body.get("display") or {})
        _set(["display", "language"], bd.get("language"))
        _set(["display", "show_cost"], bd.get("show_cost"))
        _set(["display", "streaming"], bd.get("streaming"))
        _set(["display", "theme"], bd.get("theme"))

        bmem = (body.get("memory") or {})
        _set(["memory", "memory_char_limit"], bmem.get("memory_char_limit"))
        _set(["memory", "user_char_limit"], bmem.get("user_char_limit"))

        _set(["agent", "reasoning_effort"], body.get("reasoning_effort"))

        ba = (body.get("agent") or {})
        _set(["agent", "name"], ba.get("name"))
        _set(["agent", "workspace"], ba.get("workspace"))

        bdel = (body.get("delegation") or {})
        _set(["delegation", "provider"], bdel.get("provider"))
        _set(["delegation", "model"], bdel.get("model"))

        # Dashboard behavior toggles — whitelist only known keys
        bdash = body.get("dashboard") or {}
        for k in _TOGGLE_KEYS:
            v = bdash.get(k)
            if isinstance(v, bool):
                _set(["dashboard", k], v)

        _dump_config(cfg)
        return {"ok": True}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})


@router.get("/settings/models")
async def get_models():
    cache = Path(HERMES_HOME) / "models_dev_cache.json"
    defaults = ["Claude Sonnet 4.6", "Claude Opus 4", "Claude Haiku 4", "GPT-5", "Local (LM Studio)"]
    if cache.exists():
        try:
            import json
            with open(cache, "r") as f:
                data = json.load(f)
            names = set()
            for provider_obj in data.values():
                models_dict = provider_obj.get("models") if isinstance(provider_obj, dict) else {}
                if isinstance(models_dict, dict):
                    for m in models_dict.values():
                        if isinstance(m, dict) and m.get("name"):
                            names.add(m["name"])
            if names:
                return {"models": sorted(names)}
        except Exception:
            pass
    return {"models": defaults}


@router.get("/profiles")
async def get_profiles():
    profiles_dir = Path(HERMES_HOME) / "profiles"
    if not profiles_dir.exists():
        return {"profiles": ["default"]}
    dirs = sorted(p.name for p in profiles_dir.iterdir() if p.is_dir())
    return {"profiles": dirs or ["default"]}
