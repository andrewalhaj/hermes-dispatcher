"""
delegate_toolset_floor.py — enforce a minimum toolset on child agents.

When a delegate_task call passes NO explicit toolsets, children default to
["file", "terminal"] instead of inheriting the parent's full tool set
(~32 tools, ~69 KB of schema per API call). Explicit toolsets=["web"] or
any other value on a delegate_task call is always honoured — this only
fires on the no-toolsets-specified path.

Two load paths (both idempotent):
  1. sitecustomize.py at Python startup (provider-independent)
  2. anthropic_billing_bypass.apply_patches() — belt-and-suspenders

To disable without restarting: export HERMES_DELEGATE_TOOLSET_FLOOR=off
"""
from __future__ import annotations

import os
import sys

_MARKER = "_delegate_toolset_floor_patched"
_INSTALL_STARTED = False

_DEFAULT_FLOOR: list[str] = ["file", "terminal"]

ENABLED: bool = os.environ.get("HERMES_DELEGATE_TOOLSET_FLOOR", "on").lower() not in (
    "off", "0", "false", "no",
)


def _make_wrapper(original_fn):
    """Return a drop-in replacement for _build_child_agent that injects the
    floor toolset when the caller did not specify one."""
    def _wrapped(
        task_index,
        goal,
        context,
        toolsets,
        model,
        max_iterations,
        task_count,
        parent_agent,
        **kwargs,
    ):
        effective_toolsets = toolsets
        if ENABLED and not toolsets:
            effective_toolsets = list(_DEFAULT_FLOOR)
            try:
                sys.stderr.write(
                    f"[delegate-toolset-floor] no toolsets specified — "
                    f"applying floor {_DEFAULT_FLOOR} for subagent {task_index}\n"
                )
            except Exception:
                pass
        return original_fn(
            task_index,
            goal,
            context,
            effective_toolsets,
            model,
            max_iterations,
            task_count,
            parent_agent,
            **kwargs,
        )
    return _wrapped


def _patch_module(delegate_tool_module) -> bool:
    """Wrap _build_child_agent on the given module. Idempotent."""
    if getattr(delegate_tool_module, _MARKER, False):
        return True  # already wrapped
    original = getattr(delegate_tool_module, "_build_child_agent", None)
    if not callable(original):
        sys.stderr.write(
            "[delegate-toolset-floor] _build_child_agent not found; skipping\n"
        )
        return False
    delegate_tool_module._build_child_agent = _make_wrapper(original)
    setattr(delegate_tool_module, _MARKER, True)
    sys.stderr.write(
        f"[delegate-toolset-floor] installed "
        f"(floor={_DEFAULT_FLOOR}, enabled={ENABLED})\n"
    )
    return True


def apply_patches(delegate_tool_module=None) -> bool:
    """Install the toolset-floor wrapper.

    Safe to call from sitecustomize (before tools.delegate_tool loads) and
    from anthropic_billing_bypass.apply_patches. Idempotent across callers.

    If delegate_tool_module is None and tools.delegate_tool is not yet in
    sys.modules, a MetaPathFinder is armed to patch it the moment it loads.
    """
    global _INSTALL_STARTED

    if not ENABLED:
        return False

    # Fast path: caller passes the module directly (test harness).
    if delegate_tool_module is not None:
        return _patch_module(delegate_tool_module)

    # Direct path: already loaded.
    existing = sys.modules.get("tools.delegate_tool")
    if existing is not None:
        return _patch_module(existing)

    # Deferred path: arm a MetaPathFinder — only once.
    if _INSTALL_STARTED:
        return True
    _INSTALL_STARTED = True

    try:
        from importlib.abc import MetaPathFinder
        from importlib.util import find_spec as _find_spec
    except ImportError:
        sys.stderr.write("[delegate-toolset-floor] importlib unavailable; skipping\n")
        return False

    _TARGET = "tools.delegate_tool"

    class _FloorFinder(MetaPathFinder):
        _done = False

        def find_spec(self, fullname, path=None, target=None):
            if fullname != _TARGET or self._done:
                return None
            if self in sys.meta_path:
                sys.meta_path.remove(self)
            try:
                spec = _find_spec(fullname)
            finally:
                if self not in sys.meta_path:
                    sys.meta_path.insert(0, self)
            if spec is None or spec.loader is None:
                return None
            original_exec = getattr(spec.loader, "exec_module", None)
            if not callable(original_exec):
                return None
            finder = self

            def patched_exec(module):
                original_exec(module)
                finder._done = True
                try:
                    _patch_module(module)
                except Exception as exc:
                    sys.stderr.write(
                        f"[delegate-toolset-floor] deferred patch error (no-op): "
                        f"{type(exc).__name__}: {exc}\n"
                    )

            spec.loader.exec_module = patched_exec
            return spec

    sys.meta_path.insert(0, _FloorFinder())
    sys.stderr.write("[delegate-toolset-floor] deferred finder armed\n")
    return True
