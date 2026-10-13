"""Regression tests for routes/settings.py: config sections with legacy
non-dict shapes (e.g. `model: <string>`) must not crash GET/PUT /settings.

Repro for the live 2026-10-13 AttributeError:
    routes/settings.py:52  "default": model.get("default")
    AttributeError: 'str' object has no attribute 'get'
"""

import asyncio
import importlib
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _load_settings_module(tmp_path, monkeypatch, cfg: dict):
    """Point HERMES_HOME at a tmp dir holding the given config and (re)load the module."""
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    import routes.settings as settings
    importlib.reload(settings)  # re-bind module-level HERMES_HOME
    return settings


def test_get_settings_with_str_model(tmp_path, monkeypatch):
    """`model: <str>` (legacy shorthand) must not 500; maps to default."""
    settings = _load_settings_module(tmp_path, monkeypatch, {"model": "gpt-5"})
    out = asyncio.run(settings.get_settings())
    assert out["model"] == {"default": "gpt-5", "provider": None}


def test_get_settings_with_dict_model(tmp_path, monkeypatch):
    settings = _load_settings_module(
        tmp_path, monkeypatch,
        {"model": {"default": "claude-sonnet-4-6", "provider": "anthropic"}},
    )
    out = asyncio.run(settings.get_settings())
    assert out["model"] == {"default": "claude-sonnet-4-6", "provider": "anthropic"}


def test_get_settings_with_non_dict_sections(tmp_path, monkeypatch):
    """Every section the endpoint reads must tolerate scalar/list garbage."""
    settings = _load_settings_module(tmp_path, monkeypatch, {
        "model": 42,
        "display": "dark",
        "memory": ["oops"],
        "agent": "hermes",
        "delegation": 3.14,
        "dashboard": "yes",
    })
    out = asyncio.run(settings.get_settings())
    assert out["model"] == {"default": None, "provider": None}
    assert out["display"]["theme"] is None
    assert out["dashboard"] == {}


def test_put_settings_upgrades_str_model(tmp_path, monkeypatch):
    """PUT over a legacy `model: <str>` config must not crash and must
    rewrite the section as a dict."""
    settings = _load_settings_module(tmp_path, monkeypatch, {"model": "gpt-5"})
    resp = asyncio.run(settings.put_settings(
        {"model": {"default": "claude-sonnet-4-6", "provider": "anthropic"}}
    ))
    assert resp == {"ok": True}
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert cfg["model"] == {"default": "claude-sonnet-4-6", "provider": "anthropic"}


def test_put_settings_accepts_str_model_in_body(tmp_path, monkeypatch):
    """A client sending `{"model": "gpt-5"}` (string body) is normalized."""
    settings = _load_settings_module(tmp_path, monkeypatch, {})
    resp = asyncio.run(settings.put_settings({"model": "gpt-5"}))
    assert resp == {"ok": True}
    cfg = yaml.safe_load((tmp_path / "config.yaml").read_text())
    assert cfg["model"] == {"default": "gpt-5"}
