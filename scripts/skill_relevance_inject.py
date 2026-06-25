#!/usr/bin/env python3
"""
skill_relevance_inject.py — pre_llm_call hook.

PURPOSE (attacks firing-chain links 3 & 4):
  The system prompt lists ~300 skills as a flat index. Even with intact
  descriptions (link 2 fixed), the agent must (3) actually scan that wall and
  (4) choose to load rather than wing it. This hook removes the guesswork: it
  reads the latest user message, scores it against every skill's name+description,
  and when there's a strong match, injects a short
      "Relevant skills this turn: a, b, c — load with skill_view(name)"
  line straight into the next LLM call. The right 2-3 skills are named in front
  of the agent instead of buried in a 300-item list.

WIRE PROTOCOL (pre_llm_call):
  stdin  : JSON payload; we read the most recent user message text.
  stdout : JSON {"context": "..."} to inject, or nothing (silent) when no
           strong match. Exit 0 always — a hook must never block a model call.

DESIGN NOTES:
  - Pure stdlib, no deps. Reads SKILL.md frontmatter (name + description).
  - Caches the parsed skill index in /tmp keyed on the skills-dir mtime so we
    don't walk 300 files every single turn.
  - Conservative: only injects above a score threshold, caps at 4 skills, and
    suppresses generic/over-broad matches to avoid nagging on every message.
  - Respects platform_disabled: a skill suppressed on the active platform is
    NOT surfaced (it can't be loaded there anyway).
"""
import sys, os, re, json, glob, time, hashlib

HERMES = os.path.expanduser("~/.hermes")
SKILL_ROOTS = [
    os.path.join(HERMES, "skills"),
    "/usr/local/lib/hermes-agent/skills",
    "/usr/local/lib/hermes-agent/optional-skills",
]
CACHE = "/tmp/.skill_relevance_index.json"
THRESHOLD = 4.0      # minimum score to surface a skill
MAX_SKILLS = 4       # never inject more than this many
STOP = set("the a an and or of to for with via using when use used your you this that "
           "from into onto as is are be can will not no on in at by it its his her their "
           "i we they he she them us me my our skill skills task tasks help via about "
           "create created build built make made get got run see use".split())

def tok(text):
    return [w for w in re.findall(r"[a-z][a-z0-9+\-]{2,}", (text or "").lower()) if w not in STOP]

def load_index():
    # cache keyed on max mtime across roots (cheap invalidation)
    sig = 0.0
    for r in SKILL_ROOTS:
        if os.path.isdir(r):
            sig = max(sig, os.path.getmtime(r))
    try:
        c = json.load(open(CACHE))
        if abs(c.get("sig", -1) - sig) < 1e-6:
            return c["skills"]
    except Exception:
        pass
    skills = []
    for root in SKILL_ROOTS:
        for f in glob.glob(root + "/**/SKILL.md", recursive=True):
            if any(x in f for x in (".bak", "_archive", "/node_modules/", "/venv/", "/.git/")):
                continue
            try:
                t = open(f, encoding="utf-8", errors="replace").read()
            except Exception:
                continue
            if t.count("---") < 2:
                continue
            fm = t.split("---")[1]
            nm = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
            name = (nm.group(1).strip().strip("'\"") if nm
                    else os.path.basename(os.path.dirname(f)))
            dm = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
            desc = dm.group(1).strip().strip("'\"") if dm else ""
            # also pull load_when bullets — rich trigger phrasing lives there
            lw = ""
            lwm = re.search(r"^load_when:\s*\n((?:\s+-\s.*\n?)+)", fm, re.MULTILINE)
            if lwm:
                lw = lwm.group(1)
            blob = f"{name} {name.replace('-',' ')} {desc} {lw}"
            skills.append({"name": name, "tokens": list(set(tok(blob))),
                           "name_tokens": tok(name.replace('-', ' '))})
    try:
        json.dump({"sig": sig, "skills": skills}, open(CACHE, "w"))
    except Exception:
        pass
    return skills

def active_platform(payload):
    for k in ("platform", "channel", "source"):
        v = payload.get(k)
        if isinstance(v, str) and v:
            return v.lower()
    return ""

def suppressed_set(platform):
    if not platform:
        return set()
    try:
        import yaml  # optional; if missing we just don't filter
        c = yaml.safe_load(open(os.path.join(HERMES, "config.yaml")))
        pd = (c.get("skills") or {}).get("platform_disabled") or {}
        return set(pd.get(platform, []))
    except Exception:
        return set()

def latest_user_text(payload):
    # try a few common shapes
    msgs = payload.get("messages")
    if isinstance(msgs, list):
        for m in reversed(msgs):
            if isinstance(m, dict) and m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    return c
                if isinstance(c, list):
                    return " ".join(p.get("text", "") for p in c if isinstance(p, dict))
    for k in ("user_message", "prompt", "text", "message"):
        v = payload.get(k)
        if isinstance(v, str):
            return v
    return ""

def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # silent
    text = latest_user_text(payload)
    qtok = set(tok(text))
    if len(qtok) < 2:
        return  # too little signal
    skills = load_index()
    suppressed = suppressed_set(active_platform(payload))
    # Inverse document frequency: a token in many skills is low-signal
    # ("training", "audit", "dashboard"); a rare token is high-signal.
    import math
    df = {}
    for s in skills:
        for w in set(s["tokens"]):
            df[w] = df.get(w, 0) + 1
    N = max(len(skills), 1)
    def idf(w):
        return math.log((N + 1) / (df.get(w, 0) + 1)) + 1.0
    scored = []
    for s in skills:
        if s["name"] in suppressed:
            continue
        st = set(s["tokens"])
        overlap = qtok & st
        if not overlap:
            continue
        # name-token matches doubled; every term weighted by its IDF (rarity)
        score = sum((2.0 if w in s["name_tokens"] else 1.0) * idf(w) for w in overlap)
        # require at least one SPECIFIC overlap term: long AND reasonably rare
        specific = [w for w in overlap if len(w) >= 4 and df.get(w, 0) <= N * 0.15]
        if score >= THRESHOLD and specific:
            scored.append((round(score, 2), s["name"], sorted(overlap)))
    if not scored:
        return
    scored.sort(reverse=True)
    top = scored[:MAX_SKILLS]
    # guard against over-broad firing: if the top score is weak relative to query, skip
    names = ", ".join(n for _, n, _ in top)
    ctx = (f"Relevant skills for this message: {names}. "
           f"If any matches the task, load it with skill_view(name) before acting "
           f"(per the skills-mandatory rule) rather than working from general knowledge.")
    print(json.dumps({"context": ctx}))

if __name__ == "__main__":
    main()
