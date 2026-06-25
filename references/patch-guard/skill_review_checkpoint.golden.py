"""
skill_review_checkpoint.py — per-session skill-sweep nudge for hermes-agent.
============================================================================

PURPOSE
-------
Prompt-level rules ("load skills before acting") fail silently — proven twice
in one session (built a LanceDB prototype without loading knowledge-store,
which already documented the exact pitfalls). This module injects a ONE-TIME,
per-session system-reminder into the live tool loop when a COMPLEX task starts
executing and NO skill has been loaded yet — surfacing the top matching skill
candidates so the agent loads them instead of re-deriving.

"Complex and above" is defined by the SAME classifier that upgrades
Sonnet→Opus: it reuses ``_COMPLEX_SIGNALS`` + ``_COMPLEX_SCORE_THRESHOLD`` from
anthropic_billing_bypass. One definition of complexity, two consequences
(model upgrade + skill sweep). Refinement vs the bypass: this scans ONLY
user-message text (not the system prompt, which itself contains signal words
like "audit"/"debug" and would over-fire).

TIER 2 — surfaces candidates: on fire, it name/description-matches the task
against the on-disk skill set and injects the top 2-3 skill NAMES, removing the
"which skill?" judgment. Falls back to a generic "sweep skills_list()" nudge if
nothing matches.

ARCHITECTURE (mirrors delegation_checkpoint.py — Option A)
----------------------------------------------------------
Standalone module in ~/.hermes/patches/. Two load paths (sitecustomize at
startup; chained from anthropic_billing_bypass for the Anthropic path). Both
idempotent: module-level _INSTALL_STARTED + class _MARKER.

FIRES ONCE per session when ALL hold:
  - the task (user messages) scores >= _COMPLEX_SCORE_THRESHOLD complexity signals
  - zero skill_view / skills_list calls seen this session (agent hasn't swept)
  - not already fired

DISABLE
-------
  export HERMES_SKILL_REVIEW_CHECKPOINT=off

ROLLBACK
--------
Delete this file + remove chain line from anthropic_billing_bypass.py +
remove block from sitecustomize.py + restart gateway.
"""

from __future__ import annotations

import os
import sys
import glob


# ── Tunables ─────────────────────────────────────────────────────────────────

ENABLED = os.environ.get(
    "HERMES_SKILL_REVIEW_CHECKPOINT", "on"
).strip().lower() not in {"off", "0", "false", "no", "disabled"}

_MARKER = "_skill_review_patched"
_INSTALL_STARTED = False

# Reuse the bypass's definition of "complex and above". Fallback embedded list
# only if the import fails (defensive — the patches dir is on sys.path so it
# normally resolves).
try:
    from anthropic_billing_bypass import (  # type: ignore
        _COMPLEX_SIGNALS as SIGNALS,
        _COMPLEX_SCORE_THRESHOLD as SCORE_THRESHOLD,
    )
except Exception:  # pragma: no cover - defensive fallback
    SIGNALS = [
        "refactor", "architecture", "design pattern", "design system",
        "system design", "restructure", "rebuild", "migration", "deploy",
        "production", "multi-file", "across the codebase", "end-to-end",
        "full system", "audit", "security review", "vulnerability",
        "performance analysis", "benchmark", "optimization", "from scratch",
        "build a", "implement a", "new feature", "comprehensive",
        "detailed analysis", "thorough", "write a report",
        "generate documentation", "debug", "diagnose", "root cause",
        "troubleshoot", "investigate",
    ]
    SCORE_THRESHOLD = 2

# Skill-review uses its OWN signal set + threshold, DECOUPLED from the bypass's
# Sonnet->Opus upgrade threshold. Tuning sweep-sensitivity must never alter
# model routing. The bypass SIGNALS are the base; these extras catch the
# technical-build vocabulary the upgrade list misses (the motivating LanceDB
# case tripped only "build a" = 1 against the old shared threshold of 2).
_SR_EXTRA_SIGNALS = [
    "prototype", "wire", "wire it", "wire into", "integrate", "integration",
    "semantic", "pipeline", "schema", "automate", "automation", "set up",
    "configure", "install", "dashboard", "vector", "embedding", "index",
    "ingest", "self-heal", "cron", "checkpoint", "patch", "scaffold",
]
SR_SIGNALS = list(SIGNALS) + _SR_EXTRA_SIGNALS
# Threshold 1: surface skills at the start of ANY non-trivial session. Bounded
# by latch-once-per-session + suppression the moment a skill is swept, so the
# worst case is one ignorable reminder per fresh complex session.
SR_THRESHOLD = 1

SKILLS_GLOB = os.path.expanduser("~/.hermes/skills/**/SKILL.md")

_NUDGE_WITH_CANDIDATES = (
    "\n\n[Skill checkpoint: this task scored COMPLEX and no skill has been "
    "loaded yet this session. Relevant skills detected: {candidates}. Load the "
    "matching one(s) with skill_view(name) BEFORE acting — re-deriving what a "
    "skill already documents is the reteaching trap. If none truly apply, say "
    "so briefly and proceed. Fires once per session.]"
)
_NUDGE_GENERIC = (
    "\n\n[Skill checkpoint: this task scored COMPLEX and no skill has been "
    "loaded yet this session. Sweep skills_list() and skill_view(name) any "
    "match BEFORE acting — re-deriving what a skill documents is the reteaching "
    "trap. If none apply, say so briefly and proceed. Fires once per session.]"
)

_STOPWORDS = frozenset(
    "the a an and or of to for with in on at by is are be this that use using "
    "when how into your you it its as from per not no do does set get run "
    "skill skills task tasks user agent hermes md before after".split()
)


# ── Runtime helpers ──────────────────────────────────────────────────────────

def _skill_tool_seen(assistant_message: object) -> bool:
    """True if this assistant turn called skill_view / skills_list / skill_manage."""
    try:
        tcs = getattr(assistant_message, "tool_calls", None) or []
        for tc in tcs:
            name = getattr(getattr(tc, "function", None), "name", None) or ""
            low = name.lower()
            if "skill_view" in low or "skills_list" in low or "skill_manage" in low:
                return True
    except Exception:
        pass
    return False


def _user_text(messages: list) -> str:
    """Concatenate USER-role message text only (avoids system-prompt over-fire)."""
    parts = []
    try:
        for m in messages:
            if not isinstance(m, dict) or m.get("role") != "user":
                continue
            c = m.get("content")
            if isinstance(c, str):
                parts.append(c)
            elif isinstance(c, list):
                for b in c:
                    if isinstance(b, dict):
                        parts.append(str(b.get("text") or ""))
    except Exception:
        pass
    return " ".join(parts).lower()


def _is_complex(task_text: str) -> bool:
    try:
        return sum(1 for s in SR_SIGNALS if s in task_text) >= SR_THRESHOLD
    except Exception:
        return False


def _match_skills(task_text: str, top_n: int = 3) -> list:
    """Weighted match of task vs on-disk skills. tags/name > description.

    Returns top skill names. Weighting fixes the original defect where
    knowledge-store (whose domain lives in tags: lancedb/semantic-search/
    vector-db) lost to surface description-token overlap.
    """
    try:
        words = {w for w in _tokenize(task_text) if w not in _STOPWORDS}
        if not words:
            return []
        scored = []
        for path in glob.glob(SKILLS_GLOB, recursive=True):
            try:
                name, desc, tags = _skill_meta(path)
                if not name:
                    continue
                name_w = {w for w in _tokenize(name) if w not in _STOPWORDS}
                tag_w = {w for w in _tokenize(tags) if w not in _STOPWORDS}
                desc_w = {w for w in _tokenize(desc) if w not in _STOPWORDS}
                # Weighted: a curated tag or the skill name is a far stronger
                # domain signal than an incidental description word.
                score = (
                    3 * len(words & name_w)
                    + 3 * len(words & tag_w)
                    + 1 * len(words & desc_w)
                )
                if score >= 3:  # >= one tag/name hit, or 3 description hits
                    scored.append((score, name))
            except Exception:
                continue
        scored.sort(reverse=True)
        return [n for _, n in scored[:top_n]]
    except Exception:
        return []


def _tokenize(text: str) -> set:
    """Lowercase alnum tokens. Hyphens are SEPARATORS so compound tags like
    'semantic-search' and 'lancedb-backed' split into matchable parts."""
    out = set()
    cur = []
    for ch in text.lower():
        if ch.isalnum():
            cur.append(ch)
        else:
            if len(cur) > 2:
                out.add("".join(cur))
            cur = []
    if len(cur) > 2:
        out.add("".join(cur))
    return out


def _skill_meta(path: str):
    """Read 'name:', 'description:', and 'tags:' from SKILL.md frontmatter.

    Returns (name, description, tags_str). Scans deeper than before because
    tags live under metadata.hermes.tags, several lines past description.
    """
    name = ""
    desc = ""
    tags = ""
    try:
        with open(path, encoding="utf-8") as f:
            for _ in range(40):  # frontmatter + metadata block
                line = f.readline()
                if not line:
                    break
                s = line.strip()
                if s.startswith("name:") and not name:
                    name = s.split(":", 1)[1].strip().strip("\"'")
                elif s.startswith("description:") and not desc:
                    desc = s.split(":", 1)[1].strip().strip("\"'")
                elif s.startswith("tags:") and not tags:
                    # tags: [a, b, c]  — strip brackets, keep the words
                    tags = s.split(":", 1)[1].strip().strip("[]")
                if s == "---" and name:  # end of frontmatter, but keep going
                    pass  # tags may sit in metadata block before closing ---
    except Exception:
        pass
    if not name:
        # fall back to the directory name
        name = os.path.basename(os.path.dirname(path))
    return name, desc, tags


def _append_nudge(messages: list, candidates: list) -> bool:
    try:
        if candidates:
            text = _NUDGE_WITH_CANDIDATES.format(candidates=", ".join(candidates))
        else:
            text = _NUDGE_GENERIC
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if isinstance(m, dict) and m.get("role") == "tool":
                base = m.get("content")
                base = base if isinstance(base, str) else ("" if base is None else str(base))
                m["content"] = base + text
                return True
    except Exception:
        pass
    return False


def _make_wrapper(original: object):
    def _wrapped(self, assistant_message, messages, effective_task_id, api_call_count=0):
        result = original(self, assistant_message, messages, effective_task_id, api_call_count)
        try:
            if not ENABLED:
                return result

            # Track whether the agent has engaged skills this session.
            if _skill_tool_seen(assistant_message):
                self._skill_review_loaded = True

            if getattr(self, "_skill_review_fired", False):
                return result
            if getattr(self, "_skill_review_loaded", False):
                return result  # agent already swept skills — no nudge needed

            task_text = _user_text(messages)
            if not _is_complex(task_text):
                return result

            candidates = _match_skills(task_text)
            if _append_nudge(messages, candidates):
                self._skill_review_fired = True
                try:
                    sys.stderr.write(
                        f"[skill-review-checkpoint] fired: candidates={candidates} "
                        f"session={getattr(self, 'session_id', '?')}\n"
                    )
                except Exception:
                    pass
        except Exception as exc:
            try:
                sys.stderr.write(
                    f"[skill-review-checkpoint] guard error (no-op): "
                    f"{type(exc).__name__}: {exc}\n"
                )
            except Exception:
                pass
        return result
    return _wrapped


def _patch_class(run_agent_module: object) -> bool:
    agent_cls = (
        getattr(run_agent_module, "AIAgent", None)
        or getattr(run_agent_module, "RunAgent", None)
    )
    if agent_cls is None:
        sys.stderr.write(
            "[skill-review-checkpoint] agent class (AIAgent/RunAgent) not found; skipping\n"
        )
        return False
    if getattr(agent_cls, _MARKER, False):
        return True
    original = getattr(agent_cls, "_execute_tool_calls", None)
    if not callable(original):
        sys.stderr.write(
            "[skill-review-checkpoint] _execute_tool_calls not found; skipping\n"
        )
        return False
    agent_cls._execute_tool_calls = _make_wrapper(original)
    setattr(agent_cls, _MARKER, True)
    sys.stderr.write(
        f"[skill-review-checkpoint] installed "
        f"(score>={SR_THRESHOLD}, enabled={ENABLED})\n"
    )
    return True


def apply_patches(run_agent_module: object = None) -> bool:
    global _INSTALL_STARTED
    if not ENABLED:
        return False
    if run_agent_module is not None:
        return _patch_class(run_agent_module)
    existing = sys.modules.get("run_agent")
    if existing is not None:
        return _patch_class(existing)
    if _INSTALL_STARTED:
        return True
    _INSTALL_STARTED = True
    try:
        from importlib.abc import MetaPathFinder
        from importlib.util import find_spec as _find_spec
    except ImportError:
        sys.stderr.write("[skill-review-checkpoint] importlib unavailable; skipping\n")
        return False

    class _SkillFinder(MetaPathFinder):
        _done = False

        def find_spec(self, fullname, path=None, target=None):  # type: ignore[override]
            if fullname != "run_agent" or self._done:
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

            def patched_exec(module):  # type: ignore[no-untyped-def]
                original_exec(module)
                finder._done = True
                try:
                    _patch_class(module)
                except Exception as exc:
                    sys.stderr.write(
                        f"[skill-review-checkpoint] deferred patch error (no-op): "
                        f"{type(exc).__name__}: {exc}\n"
                    )

            spec.loader.exec_module = patched_exec  # type: ignore[attr-defined]
            return spec

    sys.meta_path.insert(0, _SkillFinder())
    return True
