# ── Delegation-checkpoint guard (provider-independent startup install) ────────
# The guard logic lives in delegation_checkpoint.py (in the patches dir).
# Installing here — at Python startup — ensures it arms regardless of which
# provider the session uses, including DeepSeek-only sessions that never touch
# the Anthropic adapter. The installer is idempotent: if an Anthropic session
# later chains through anthropic_billing_bypass.apply_patches(), the second
# call is a no-op.
#
# To disable: export HERMES_DELEG_CHECKPOINT=off
try:
    import delegation_checkpoint as _deleg_dc
    _deleg_dc.apply_patches()
except Exception as _deleg_exc:
    sys.stderr.write(
        f"[delegation-checkpoint] sitecustomize install failed (no-op): "
        f"{type(_deleg_exc).__name__}: {_deleg_exc}\n"
    )


# ── Skill-review checkpoint (provider-independent startup install) ────────────
# Surfaces matching skill candidates on COMPLEX tasks when no skill has been
# loaded yet this session. Same startup-install rationale as the delegation
# guard above: arms regardless of provider, idempotent across chained callers.
#
# To disable: export HERMES_SKILL_REVIEW_CHECKPOINT=off
try:
    import skill_review_checkpoint as _skill_src
    _skill_src.apply_patches()
except Exception as _skill_exc:
    sys.stderr.write(
        f"[skill-review-checkpoint] sitecustomize install failed (no-op): "
        f"{type(_skill_exc).__name__}: {_skill_exc}\n"
    )


# ── Memory-checkpoint guard (provider-independent startup install) ────────────
# Appends an in-band nudge to the tool result on every memory add/replace that
# pushes a store above the warn threshold (default 88%). Fires at the exact
# moment of the write, while the agent still has full context to compact.
#
# To disable: export HERMES_MEMORY_CHECKPOINT=off
try:
    import memory_checkpoint as _mem_mc
    _mem_mc.apply_patches()
except Exception as _mem_exc:
    sys.stderr.write(
        f"[memory-checkpoint] sitecustomize install failed (no-op): "
        f"{type(_mem_exc).__name__}: {_mem_exc}\n"
    )


# ── Domain-ownership guard (provider-independent startup install) ─────────────
# Nudges when a state-changing ssh/scp targets a peer-owned host/path (map:
# ~/.hermes/references/domain-ownership.json). Fires on the FIRST owned write,
# before momentum exists; suppressed once a kanban card is dispatched to the owner.
#
# To disable: export HERMES_DOMAIN_CHECKPOINT=off
try:
    import domain_ownership_checkpoint as _dom_doc
    _dom_doc.apply_patches()
except Exception as _dom_exc:
    sys.stderr.write(
        f"[domain-ownership-checkpoint] sitecustomize install failed (no-op): "
        f"{type(_dom_exc).__name__}: {_dom_exc}\n"
    )


# ── Write-gate guard (provider-independent startup install) ───────────────────
# Hard-enforcement gate on gated terminal commands and file writes to protected
# paths. Blocks unless armed via explicit user greenlight (token file).
# Modes: block (default) or warn. Same startup-install rationale as other guards:
# arms regardless of provider, idempotent across chained callers.
#
# To disable: export HERMES_WRITE_GATE=off
# To warn-only: export HERMES_WRITE_GATE_MODE=warn
try:
    import write_gate as _wg_wg
    _wg_wg.apply_patches()
except Exception as _wg_exc:
    sys.stderr.write(
        f"[write-gate] sitecustomize install failed (no-op): "
        f"{type(_wg_exc).__name__}: {_wg_exc}\n"
    )


# ── Delegate toolset floor (provider-independent startup install) ─────────────
# When a delegate_task call passes no explicit toolsets, children default to
# ["file", "terminal"] instead of inheriting the full parent tool set.
# Explicit toolsets=["web"] etc. on a call are always honoured.
#
# To disable: export HERMES_DELEGATE_TOOLSET_FLOOR=off
try:
    import delegate_toolset_floor as _dtf
    _dtf.apply_patches()
except Exception as _dtf_exc:
    sys.stderr.write(
        f"[delegate-toolset-floor] sitecustomize install failed (no-op): "
        f"{type(_dtf_exc).__name__}: {_dtf_exc}\n"
    )
