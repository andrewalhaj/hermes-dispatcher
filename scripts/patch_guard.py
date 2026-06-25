#!/usr/bin/env python3
"""
patch_guard.py — self-heal watchdog for the OAuth-bypass + delegation-guard
============================================================================

WHY THIS EXISTS
---------------
The three patch artifacts live in files that get OVERWRITTEN by routine ops:
  - ~/.hermes/patches/anthropic_billing_bypass.py  -> clobbered by
    hermes-claude-auth install.sh (it ships a vanilla version WITHOUT the
    complexity classifier). Proven 2026-06-06.
  - venv .../sitecustomize.py                       -> rebuilt by `hermes
    update` (venv rebuild) AND by install.sh.
  - ~/.hermes/patches/delegation_checkpoint.py      -> our own file; only at
    risk if the patches dir is wiped.

When clobbered, failures are SILENT: complex tasks quietly stop upgrading to
Opus, and the delegation nudge quietly stops firing. Nobody notices until a
bill or an audit says so.

WHAT IT DOES
------------
Compares each live file against a known-good GOLDEN copy under
~/.hermes/references/patch-guard/ by checking for required MARKERS (not a raw
diff — markers survive harmless upstream churn). On drift:
  1. Backs up the drifted live file (.bak-<ts>-driftheal).
  2. Restores from golden (bypass, deleg) OR re-appends our block
     (sitecustomize — the rest of that file is managed by install.sh).
  3. Validates Python syntax of the result.
  4. Emits a report to stdout (the cron delivers it verbatim).

SILENT WHEN HEALTHY: prints nothing and exits 0 if all markers present, so the
no_agent cron stays quiet (the watchdog pattern).

DOES NOT auto-restart the gateway. A background job bouncing the gateway would
be surprising and could interrupt an active session. Instead it tells Andrew
the exact restart command — the restored files load on the next gateway start.
"""

import ast
import os
import sys
import time

PATCHES = "/root/.hermes/patches"
GOLDEN = "/root/.hermes/references/patch-guard"
SITECUSTOMIZE = (
    "/usr/local/lib/hermes-agent/venv/lib/python3.11/site-packages/sitecustomize.py"
)

TS = time.strftime("%Y%m%d-%H%M%S")
actions = []   # human-readable lines describing what was healed
problems = []  # things we could NOT heal (need attention)


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as exc:
        return None


def _backup(path, tag):
    try:
        data = _read(path)
        if data is not None:
            with open(f"{path}.bak-{TS}-{tag}", "w", encoding="utf-8") as f:
                f.write(data)
            return True
    except Exception:
        pass
    return False


def _valid_py(path):
    src = _read(path)
    if src is None:
        return False
    try:
        ast.parse(src)
        return True
    except SyntaxError:
        return False


def _restore_full(name, live, golden, markers):
    """Restore a whole file from golden if any required marker is missing."""
    src = _read(live)
    golden_src = _read(golden)
    if golden_src is None:
        problems.append(f"{name}: GOLDEN MISSING at {golden} — cannot self-heal")
        return
    missing = [m for m in markers if src is None or m not in src]
    if not missing:
        return  # healthy
    _backup(live, "driftheal")
    try:
        with open(live, "w", encoding="utf-8") as f:
            f.write(golden_src)
    except Exception as exc:
        problems.append(f"{name}: restore write failed: {type(exc).__name__}: {exc}")
        return
    if not _valid_py(live):
        problems.append(f"{name}: restored file FAILED syntax check — investigate")
        return
    actions.append(
        f"{name}: missing marker(s) {missing} -> restored from golden "
        f"({len(golden_src.splitlines())} lines)."
    )


def _heal_sitecustomize():
    """sitecustomize is managed by install.sh — only ensure OUR block is present.
    If install.sh rebuilt it, the hermes-claude-auth hook is present but our
    delegation block is gone. Re-append it. Never overwrite the whole file."""
    name = "sitecustomize.py"
    live = _read(SITECUSTOMIZE)
    block = _read(os.path.join(GOLDEN, "sitecustomize-block.golden.py"))
    if block is None:
        problems.append(f"{name}: golden block missing — cannot self-heal")
        return
    if live is None:
        problems.append(f"{name}: live file unreadable at {SITECUSTOMIZE}")
        return
    # Our marker — require all guards present (they append as one block).
    if "delegation_checkpoint" in live and "skill_review_checkpoint" in live and "write_gate" in live and "delegate_toolset_floor" in live:
        return  # our block present — healthy
    # Sanity: don't append into a file that lost the bypass hook entirely —
    # that means install.sh hasn't run yet / bigger problem.
    if "hermes-claude-auth managed" not in live:
        problems.append(
            f"{name}: bypass hook ALSO missing — run hermes-claude-auth "
            f"install.sh first, then this watchdog will append our block."
        )
        return
    _backup(SITECUSTOMIZE, "driftheal")
    try:
        with open(SITECUSTOMIZE, "a", encoding="utf-8") as f:
            f.write(block)
    except Exception as exc:
        problems.append(f"{name}: append failed: {type(exc).__name__}: {exc}")
        return
    if not _valid_py(SITECUSTOMIZE):
        problems.append(f"{name}: re-appended block broke syntax — investigate")
        return
    actions.append(f"{name}: delegation block was missing -> re-appended.")


# ── Honcho drift-suppression patch (UPSTREAM file — surgical re-apply, NOT whole-file restore) ──
# honcho/__init__.py is a 61KB upstream module that `hermes update` legitimately
# rewrites. A whole-file golden restore would clobber upstream changes, so on drift
# we re-apply ONLY the 2-block comment-out to the CURRENT file via string replace.
HONCHO_INIT = "/usr/local/lib/hermes-agent/plugins/memory/honcho/__init__.py"
HONCHO_MARKER = "HERMES-PATCH drift-suppression"

_HONCHO_TARGET = (
    '        rep = ctx.get("representation", "")\n'
    '        if rep:\n'
    '            parts.append(f"## User Representation\\n{rep}")\n'
    '\n'
    '        card = ctx.get("card", "")\n'
    '        if card:\n'
    '            parts.append(f"## User Peer Card\\n{card}")\n'
    '\n'
    '        ai_rep = ctx.get("ai_representation", "")'
)

_HONCHO_REPLACEMENT = (
    '        # HERMES-PATCH drift-suppression: user-side `representation`/`card` are the\n'
    '        # server-side DIALECTIC objects (directional `root` peer), re-derived every\n'
    '        # turn from an undeletable observation log — carry stale confabulations that\n'
    '        # counter-evidence/curated-card overwrites cannot stop (this path never reads\n'
    '        # the curated card at peer 8878729385). Dropped from per-turn injection; the\n'
    '        # clean curated card is read on demand via honcho_profile(peer="8878729385").\n'
    '        # rep = ctx.get("representation", "")   # DROPPED (dirty observation dump)\n'
    '        # card = ctx.get("card", "")            # DROPPED (dirty dialectic-derived card on root peer)\n'
    '\n'
    '        ai_rep = ctx.get("ai_representation", "")'
)


def _heal_honcho_format():
    """Re-apply the drift-suppression patch to honcho/__init__.py if a `hermes
    update` reverted it. Surgical (string replace on current file), never a
    whole-file restore — so upstream changes are preserved."""
    name = "honcho/__init__.py"
    src = _read(HONCHO_INIT)
    if src is None:
        problems.append(f"{name}: live file unreadable at {HONCHO_INIT}")
        return
    if HONCHO_MARKER in src:
        return  # patch present — healthy
    # Marker gone (likely hermes update). Re-apply ONLY if the exact upstream
    # target block is present; otherwise upstream refactored the function and a
    # human must re-port the patch.
    if _HONCHO_TARGET not in src:
        problems.append(
            f"{name}: drift-suppression marker MISSING and target block not found "
            f"— upstream likely refactored _format_first_turn_context; re-port patch manually."
        )
        return
    _backup(HONCHO_INIT, "driftheal")
    new_src = src.replace(_HONCHO_TARGET, _HONCHO_REPLACEMENT, 1)
    try:
        with open(HONCHO_INIT, "w", encoding="utf-8") as f:
            f.write(new_src)
    except Exception as exc:
        problems.append(f"{name}: re-patch write failed: {type(exc).__name__}: {exc}")
        return
    if not _valid_py(HONCHO_INIT):
        problems.append(f"{name}: re-patched file FAILED syntax check — investigate")
        return
    actions.append(
        f"{name}: drift-suppression patch was reverted -> re-applied "
        f"(user representation+card injection commented out)."
    )


# ── B-full auto-retrieval patch (UPSTREAM file — surgical re-apply) ──
# gateway/run.py is a ~20k-line upstream module that `hermes update` rewrites.
# Whole-file restore would clobber upstream changes, so on drift we re-insert
# ONLY our two blocks (the cached engine helpers + the injection call) at their
# anchors. Golden text lives in references/patch-guard/bfull-*.golden.py.
BFULL_RUN = "/usr/local/lib/hermes-agent/gateway/run.py"
BFULL_MARKER = "_bfull_retrieve(message_text)"
_BFULL_HELPERS_ANCHOR = "logger = logging.getLogger(__name__)"
_BFULL_INJECT_ANCHOR = (
    "        if message_text is None:\n"
    "            return\n"
)


def _heal_bfull():
    """Re-apply the B-full auto-retrieval patch to gateway/run.py if a `hermes
    update` reverted it. Surgical (string insert on current file), never a
    whole-file restore — so upstream changes are preserved."""
    name = "gateway/run.py"
    src = _read(BFULL_RUN)
    if src is None:
        problems.append(f"{name}: live file unreadable at {BFULL_RUN}")
        return
    if BFULL_MARKER in src:
        return  # patch present — healthy
    helpers = _read(os.path.join(GOLDEN, "bfull-helpers.golden.py"))
    inject = _read(os.path.join(GOLDEN, "bfull-injection.golden.py"))
    if helpers is None or inject is None:
        problems.append(f"{name}: golden B-full snippet(s) missing — cannot self-heal")
        return
    if _BFULL_HELPERS_ANCHOR not in src or _BFULL_INJECT_ANCHOR not in src:
        problems.append(
            f"{name}: B-full marker MISSING and an anchor not found "
            f"— upstream likely refactored run.py; re-port patch manually."
        )
        return
    _backup(BFULL_RUN, "driftheal")
    # Insert helpers right AFTER the logger line (module scope), and the
    # injection block right AFTER the message_text-None guard (method scope).
    new_src = src.replace(
        _BFULL_HELPERS_ANCHOR,
        _BFULL_HELPERS_ANCHOR + helpers,
        1,
    )
    new_src = new_src.replace(
        _BFULL_INJECT_ANCHOR,
        _BFULL_INJECT_ANCHOR + inject,
        1,
    )
    try:
        with open(BFULL_RUN, "w", encoding="utf-8") as f:
            f.write(new_src)
    except Exception as exc:
        problems.append(f"{name}: re-patch write failed: {type(exc).__name__}: {exc}")
        return
    if not _valid_py(BFULL_RUN):
        problems.append(f"{name}: re-patched file FAILED syntax check — investigate")
        return
    actions.append(
        f"{name}: B-full auto-retrieval patch was reverted -> re-applied "
        f"(per-turn cold-store injection restored)."
    )


# tools/delegate_tool.py — `hermes update` rewrites this core file, reverting our
# subagent api_key fallback. Surgical re-insert of ONE block at its anchor (never a
# whole-file restore — preserves upstream changes). Golden in delegate-tool-fallback.golden.py.
DELEGATE_RUN = "/usr/local/lib/hermes-agent/tools/delegate_tool.py"
DELEGATE_MARKER = "Fallback: when parent inheritance produces a falsy key"
_DELEGATE_ANCHOR = "    effective_api_key = override_api_key or parent_api_key\n"


def _heal_delegate_tool():
    """Re-apply the subagent api_key fallback to tools/delegate_tool.py if a
    `hermes update` reverted it. Surgical anchor-insert, never whole-file."""
    name = "tools/delegate_tool.py"
    src = _read(DELEGATE_RUN)
    if src is None:
        problems.append(f"{name}: live file unreadable at {DELEGATE_RUN}")
        return
    if DELEGATE_MARKER in src:
        return  # patch present — healthy
    inject = _read(os.path.join(GOLDEN, "delegate-tool-fallback.golden.py"))
    if inject is None:
        problems.append(f"{name}: golden delegate-tool snippet missing — cannot self-heal")
        return
    if _DELEGATE_ANCHOR not in src:
        problems.append(
            f"{name}: fallback marker MISSING and anchor not found "
            f"— upstream likely refactored delegate_tool.py; re-port patch manually."
        )
        return
    _backup(DELEGATE_RUN, "driftheal")
    # Insert the fallback block right AFTER the effective_api_key assignment.
    new_src = src.replace(_DELEGATE_ANCHOR, _DELEGATE_ANCHOR + inject.lstrip("\n"), 1)
    try:
        with open(DELEGATE_RUN, "w", encoding="utf-8") as f:
            f.write(new_src)
    except Exception as exc:
        problems.append(f"{name}: re-patch write failed: {type(exc).__name__}: {exc}")
        return
    if not _valid_py(DELEGATE_RUN):
        problems.append(f"{name}: re-patched file FAILED syntax check — investigate")
        return
    actions.append(
        f"{name}: subagent api_key fallback was reverted -> re-applied "
        f"(delegation credential inheritance restored)."
    )


# ── Run checks ───────────────────────────────────────────────────────────────
# 1. Bypass: must have BOTH the complexity classifier AND the deleg chain line.
_restore_full(
    "anthropic_billing_bypass.py",
    os.path.join(PATCHES, "anthropic_billing_bypass.py"),
    os.path.join(GOLDEN, "anthropic_billing_bypass.golden.py"),
    markers=["_classify_complexity", "import delegation_checkpoint", "import skill_review_checkpoint", "import memory_checkpoint", "import domain_ownership_checkpoint", "import write_gate", "import delegate_toolset_floor"],
)

# 2. Delegation guard standalone module.
_restore_full(
    "delegation_checkpoint.py",
    os.path.join(PATCHES, "delegation_checkpoint.py"),
    os.path.join(GOLDEN, "delegation_checkpoint.golden.py"),
    markers=["def apply_patches", "_deleg_checkpoint_patched"],
)

# 2b. Skill-review guard standalone module.
_restore_full(
    "skill_review_checkpoint.py",
    os.path.join(PATCHES, "skill_review_checkpoint.py"),
    os.path.join(GOLDEN, "skill_review_checkpoint.golden.py"),
    markers=["def apply_patches", "_skill_review_patched"],
)

# 2c. Memory-checkpoint guard standalone module.
_restore_full(
    "memory_checkpoint.py",
    os.path.join(PATCHES, "memory_checkpoint.py"),
    os.path.join(GOLDEN, "memory_checkpoint.golden.py"),
    markers=["def apply_patches", "_memory_checkpoint_patched"],
)

# 2d. Domain-ownership guard standalone module.
_restore_full(
    "domain_ownership_checkpoint.py",
    os.path.join(PATCHES, "domain_ownership_checkpoint.py"),
    os.path.join(GOLDEN, "domain_ownership_checkpoint.golden.py"),
    markers=["def apply_patches", "_domain_ownership_patched"],
)

# 2e. Write-gate guard standalone module.
_restore_full(
    "write_gate.py",
    os.path.join(PATCHES, "write_gate.py"),
    os.path.join(GOLDEN, "write_gate.golden.py"),
    markers=["def apply_patches", "_write_gate_patched"],
)

# 2f. Kanban-checkpoint guard standalone module.
# Two markers: the nudge layer (_kanban_checkpoint_patched) AND the whole-objective
# enforcement layer (_objgate_should_block). A heal fires if EITHER goes missing —
# so stripping just the pre-execution objgate while leaving the nudge intact still
# triggers a restore from golden.
_restore_full(
    "kanban_checkpoint.py",
    os.path.join(PATCHES, "kanban_checkpoint.py"),
    os.path.join(GOLDEN, "kanban_checkpoint.golden.py"),
    markers=["def apply_patches", "_kanban_checkpoint_patched", "_objgate_should_block"],
)

# 2g. Delegate toolset floor — enforces ["file", "terminal"] as the default child
# toolset when delegate_task is called without explicit toolsets. Prevents children
# from inheriting the full ~32-tool parent schema on every API call.
_restore_full(
    "delegate_toolset_floor.py",
    os.path.join(PATCHES, "delegate_toolset_floor.py"),
    os.path.join(GOLDEN, "delegate_toolset_floor.golden.py"),
    markers=["def apply_patches", "_delegate_toolset_floor_patched"],
)

# 2h. Cold-store schema guard — validates every write to the Supabase cold store
# (knowledge.py store() and store_contextualized()) before the Supabase insert.
# Fail-closed: rejects on narrative/affect/methodology genre. Audit-logs every decision.
# This guard lives in a SCRIPT (not a patch), so _restore_full targets the script path.
# markers: the unique HERMES-GUARD token plus the two chokepoints it guards.
_restore_full(
    "knowledge.py (cold-store-guard)",
    os.path.join(os.path.dirname(PATCHES), "scripts", "knowledge.py"),
    os.path.join(GOLDEN, "knowledge.golden.py"),
    markers=["HERMES-GUARD cold-store-validator", "_coldstore_validate", "store_contextualized"],
)

# 3. sitecustomize block (append-only heal).
_heal_sitecustomize()

# 4. Honcho drift-suppression patch (surgical re-apply on upstream file).
_heal_honcho_format()

# 5. B-full auto-retrieval patch (surgical re-apply on upstream run.py).
_heal_bfull()

# 6. Subagent api_key fallback (surgical re-apply on upstream delegate_tool.py).
_heal_delegate_tool()


# ── Report (silent if nothing happened) ──────────────────────────────────────
if actions or problems:
    out = ["🩹 Patch-guard self-heal triggered:"]
    for a in actions:
        out.append(f"  ✅ {a}")
    for p in problems:
        out.append(f"  ❌ {p}")
    if actions:
        out.append(
            "\n⚠️ Restored files load on next gateway start. To activate now:\n"
            "  systemctl --user restart hermes-gateway.service hermes-gateway-ha-bot.service"
        )
    print("\n".join(out))
    sys.exit(0)

# Healthy: print nothing -> cron stays silent.
sys.exit(0)
