# hermes-dispatcher — Batch 2 Security Scheme Proposals

**Status:** PROPOSALS ONLY. None applied. All are behavior-changing and greenlight-gated per the POLA refactor prompt §2.3/§3.A.
**Against:** `master` @ 8cdc706 (post Batch-1 merge).
**Rule:** each is its own commit on its own branch; none bundled with cosmetics.

---

## A1b — Replace unsalted SHA-256 with a salted KDF (Argon2id or bcrypt)

**Current (routes/auth.py:40):** `hashlib.sha256(submitted.encode()).hexdigest()` compared to a stored 64-hex digest. Unsalted, fast → vulnerable to rainbow-table / GPU brute-force if the hash leaks.

**Proposed:** bcrypt (stdlib-adjacent, single dep `bcrypt`) or Argon2id (`argon2-cffi`). bcrypt is simpler and battle-tested; recommend it.

**Diff sketch (routes/auth.py):**
```python
import bcrypt
# at import: store the bcrypt hash bytes
_PASSWORD_HASH: bytes = _HASH_FILE.read_bytes().strip()  # now a $2b$... bcrypt hash

# in login():
ok = bcrypt.checkpw(submitted.encode(), _PASSWORD_HASH)
if not ok:
    await asyncio.sleep(0.5)
    return JSONResponse({"ok": False, "error": "Invalid password"}, status_code=401)
```

**Migration required:** the existing `.dashboard_passwd_hash` is a SHA-256 digest; bcrypt can't read it. Must regenerate:
```
python -c "import bcrypt; open('.dashboard_passwd_hash','wb').write(bcrypt.hashpw(b'<password>', bcrypt.gensalt()))"
```
**Dependency:** `bcrypt` added to requirements.txt (one-line justification: industry-standard password KDF; no stdlib equivalent).
**Coupled with A2b:** since the hash file must be rewritten anyway, do A1b + A2b together (rotation is free during the bcrypt migration).
**Risk:** if the new hash isn't written before deploy, login breaks (loud, immediate — login returns 401 for all). Rollback: restore SHA-256 hash + revert code.
**Behavior-changing:** y. **Greenlight:** required.

---

## A2b — Actually untrack + rotate the committed password hash

**Current state (verified):** `.dashboard_passwd_hash` is STILL git-tracked in HEAD. The Batch-1 `.gitignore` entry only prevents *future* adds — git does not untrack already-tracked files from a `.gitignore` change. The live SHA-256 hash sits in HEAD AND in history (commits db3ad41, ddf87f2, 09bd1d1, 9ff08ec).

**Proposed, in order:**

1. **Untrack from HEAD** (keeps the local file, stops tracking it):
   ```
   git rm --cached .dashboard_passwd_hash
   git commit -m "security: untrack committed password hash (A2b)"
   ```
   After this, the file stays on disk (auth.py reads it at import) but is no longer in the repo going forward. This is low-risk and reversible — recommend doing this one regardless of the others.

2. **Rotate the credential** (the hash was public in the repo, so the password behind it should be considered compromised). Generate a new hash (bcrypt if A1b lands, else SHA-256), write it to the now-untracked file, and the old digest becomes worthless.

3. **History scrub (optional, heaviest):** the old hash remains in git history even after untracking. To purge it requires `git filter-repo` (or BFG) + a force-push that rewrites history — this breaks every existing clone and is destructive. **Recommendation: skip the scrub, just rotate.** Once the credential is rotated, the historical hash protects nothing. Only scrub if repo history is shared publicly AND the password can't be rotated for some reason.

**Risk:** step 1 is safe (file stays on disk). Step 2 requires re-entering the new password in the browser. Step 3 is destructive (history rewrite) — gated separately, not recommended.
**Behavior-changing:** step 1 no (transparent), step 2 yes (password changes), step 3 yes (history). **Greenlight:** required for 2 and 3; 1 is low-risk but still your call.

---

## A3b — Per-session tokens with server-side expiry

**Current (routes/auth.py:25):** one process-global `SESSION_TOKEN = secrets.token_hex(32)`. All clients share it; never expires; logout only clears the client cookie (token stays valid server-side until restart).

**Proposed:** a server-side dict of `{token: expiry_timestamp}`; login mints a fresh token per session; logout deletes it server-side; the auth middleware checks membership + TTL.

**Diff sketch (routes/auth.py):**
```python
import time
_SESSIONS: dict[str, float] = {}        # token -> expiry epoch
_TTL = 7 * 24 * 3600                     # 7 days

def _new_session() -> str:
    tok = secrets.token_hex(32)
    _SESSIONS[tok] = time.time() + _TTL
    return tok

def _valid(tok: str) -> bool:
    exp = _SESSIONS.get(tok)
    if exp is None: return False
    if time.time() > exp:
        _SESSIONS.pop(tok, None); return False
    return True

# login(): value=_new_session()
# logout(): _SESSIONS.pop(request.cookies.get("hd_session"), None) then delete cookie
# check(): return _valid(cookie)
```
**Also touches server.py:** the `auth_gate` middleware imports `SESSION_TOKEN` and does `cookie == SESSION_TOKEN`. Must change to `from routes.auth import _valid` and `_valid(cookie)`.
**Tradeoff:** tokens live in memory → wiped on restart (all clients re-login). That's the same blast radius as today (restart already invalidates the global token), so no regression. For persistence across restarts, back `_SESSIONS` with state.db (heavier — separate proposal).
**Risk:** middleware coupling — both files must change together or auth breaks. Loud failure (everything 401s). Rollback: revert both.
**Behavior-changing:** y (real logout, expiry, multi-client isolation). **Greenlight:** required.

---

## A4b — Tighten CORS from wildcard to an explicit allowlist

**Current (server.py:45):** `allow_origins=["*"]` on a cookie-authed app. Mitigated today by `samesite="strict"` + `httponly=True`, but `*` is broad for a credentialed API.

**Proposed:** drive the allowlist from an env var (defaults to localhost + the Tailscale origin), so a publicly-exposed instance can lock it down without a code change.

**Diff sketch (server.py):**
```python
import os
_origins = os.environ.get(
    "DASHBOARD_CORS_ORIGINS",
    "http://localhost:8787,http://127.0.0.1:8787",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,   # needed for cookie auth once origins are explicit
    allow_methods=["*"],
    allow_headers=["*"],
)
```
**Note:** `allow_credentials=True` is invalid with `allow_origins=["*"]` (the browser rejects it) — which is itself a latent bug in the current config: cookies work today only because same-origin requests don't trigger CORS preflight. Moving to an explicit allowlist *fixes* that and makes credentialed cross-origin correct.
**Operational dependency:** must know the real deployment origin(s) at config time. Default covers localhost; add the Tailscale hostname/IP origin via the env var.
**Risk:** if an origin the browser actually uses isn't in the list, the dashboard's fetches start failing CORS (visible in console, recoverable by adding the origin). Rollback: revert to `["*"]`.
**Behavior-changing:** y. **Greenlight:** required + need the deployment origin(s) from you.

---

## Recommended sequencing

1. **A2b step 1** (untrack) — safe, do anytime, even alone.
2. **A1b + A2b step 2** together — bcrypt migration rewrites the hash, so rotate in the same move. One branch, two coupled commits.
3. **A3b** — independent of the above; its own branch.
4. **A4b** — independent; needs the deployment origin from you before I can set a non-default allowlist.
5. **A2b step 3 (history scrub)** — skip unless you specifically want it; destructive force-push.

Each lands on its own branch → PR → your squash-merge, same flow as Batch 1.
