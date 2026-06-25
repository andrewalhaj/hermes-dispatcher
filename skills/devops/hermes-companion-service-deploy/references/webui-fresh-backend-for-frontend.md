# Building a fresh standalone backend to fit an untouched frontend

Distinct from `webui-custom-spa-frontend.md`. That reference covers wiring a
redesigned SPA onto the EXISTING `nesquena/hermes-webui` backend. THIS one covers
the harder variant the user asked for (verified 2026-06-18):

> "Keep the front end as is and adapt the back end to fit it. Provide dummy data
>  in spots where it can't. Do not use that backend — create a new one. Follow
>  the README. If it asks for something you're missing, build it."

i.e. the frontend is the source of truth and stays **byte-identical**; you author
a brand-new minimal backend that serves it and provides the APIs the README's
"Wiring" section names. Use this when the user rejects edits to the frontend and
rejects reusing the upstream Python backend.

## Decision rule

- "Wire the frontend to the backend" → use `webui-custom-spa-frontend.md` (edit
  `store.tsx`/`api.ts`, deploy `dist/` into upstream `static/`).
- "Keep the frontend as-is, build a new backend to fit it" → THIS file. Do NOT
  touch any `src/` file except where the README explicitly says (`mockData.ts`,
  `store.tsx`). Re-extract the zip clean and `md5sum` against the archive to PROVE
  the frontend is untouched before building.

## The mocked-frontend reality

The `hermes-react` design build makes **zero** API calls — all data is static in
`src/lib/mockData.ts`, consumed through `src/lib/store.tsx`. `grep -rn "fetch\|
EventSource\|/api/"` across `src/` returns nothing but a log-fixture string. So
"adapt the backend to fit it" means: stand up endpoints at the paths the README's
Wiring section documents, and (if keeping the frontend truly untouched) leave the
mock store in place — the backend exists to serve the built bundle and answer the
documented routes for when the store IS later pointed at them. Provide dummy data
for anything with no real source (insights, settings).

## Asset path: serve `/assets/`, NOT `/static/` — the opposite of the SPA-wiring case

When the frontend is **untouched**, its `vite.config.ts` has no `base` override,
so the built `index.html` references `/assets/index-<hash>.js`. The fresh backend
must mount static at `/assets`:
```python
app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")
```
Do NOT add `base: '/static/'` here — that's only correct when dropping `dist/`
into the upstream webui's `/static/`-rooted server. Mounting the wrong root gives
the same silent blank-white-page as the SPA-wiring base bug. Confirm the path the
HTML actually references 200s: `curl .../assets/<hash>.js`.

## No `itsdangerous` in the hermes venv → no Starlette SessionMiddleware

`/usr/local/lib/hermes-agent/venv` ships fastapi + starlette + uvicorn +
sse-starlette + aiohttp + tornado, but NOT `itsdangerous`, which
`starlette.middleware.sessions.SessionMiddleware` imports at module load. Adding
it crashes the server on boot with `ModuleNotFoundError: No module named
'itsdangerous'`. Don't pip-install it — roll a stdlib HMAC-signed cookie instead
(hmac + hashlib + secrets are all stdlib):
```python
COOKIE_NAME = "hermes_session"
def _sign(v: str) -> str:
    return hmac.new(SECRET_KEY.encode(), v.encode(), hashlib.sha256).hexdigest()
def _make_session_token() -> str:
    t = secrets.token_hex(16); return f"{t}.{_sign(t)}"
def _verify_session_token(c: str) -> bool:
    if not c or "." not in c: return False
    t, sig = c.rsplit(".", 1); return hmac.compare_digest(sig, _sign(t))
# login: response.set_cookie(COOKIE_NAME, _make_session_token(),
#         max_age=..., httponly=True, samesite="lax")
# auth check: _verify_session_token(request.cookies.get(COOKIE_NAME, ""))
```
Always check what the venv actually has before reaching for a middleware:
`venv/bin/pip list | grep -iE 'flask|fastapi|starlette|uvicorn|aiohttp|itsdangerous'`.

## Serve the SPA at `/` AND a catch-all WITHOUT an auth redirect

The design frontend has NO login screen — auth is enforced at the API layer only.
So `GET /` and the SPA catch-all must serve `index.html` unconditionally (no
`_check_auth`), and only the `/api/*` routes gate. If you gate the page load you
get a 302 loop to a `/login` that doesn't exist. The login flow is: SPA boots →
its API calls 401 → (the frontend would show a prompt; the mock store just renders
fixtures) → `POST /api/auth/login {password}` sets the cookie → subsequent API
calls authorize.

## The port-not-freed trap on rebuild

`systemctl stop hermes-webui` does NOT always kill a Python server that was started
as a **foreground** process earlier in the session (e.g. a survived bootstrap or a
prior manual launch) — that process keeps holding `0.0.0.0:8787`, so the new
systemd unit fails to bind and you see stale data + "Invalid password" (you're
hitting the OLD server). Diagnose with `ss -tlnp | grep 8787` then
`cat /proc/<pid>/cmdline | tr '\0' ' '` to see which server.py owns it. Kill the
stray PID, then `systemctl restart`. Confirm `ss -tlnp` shows the NEW MainPID.

## Real data sources the fresh backend can tap (same as the upstream uses)

- **Kanban:** `sys.path.insert(0,"/usr/local/lib/hermes-agent")` then
  `from hermes_cli import kanban_db as kb; kb.init_db()`; query the `tasks` table
  with `kb.connect_closing()`. Filter `status != 'archived'`. `task_skills` and
  `task_dependencies` tables hold skills[] / parents[]. PATCH writes back with an
  `UPDATE tasks SET ... WHERE id=?` + `conn.commit()`.
- **Memory:** read `~/.hermes/memories/MEMORY.md`, `USER.md`, `SOUL.md` as text.
- **Sessions:** enumerate `~/.hermes/webui/sessions/*.json`, sort by mtime.
- **Logs:** `journalctl -u hermes-gateway -n 100 -o json`, map fields.
- **Chat SSE:** try `gateway.run.run_agent_streaming(...)`; on import/runtime error
  fall back to a subprocess `python -m hermes_cli --session ... --message ...
  --stream` and chunk stdout word-by-word into `delta` events; always end with a
  `done` event. Provide an `[Agent unavailable: ...]` delta if both paths fail so
  the UI never hangs.
- **Insights / settings:** no clean real source → return dummy shapes that match
  what the panels render (KPIs, 14-day activity array, model-mix array).

## systemd unit shape

Point at the new project dir, read secrets from an `EnvironmentFile=` (keeps the
password out of the unit), run `server.py` directly under the agent venv python:
```ini
[Service]
WorkingDirectory=/root/projects/<new-backend>
EnvironmentFile=/root/projects/<new-backend>/.env
ExecStart=/usr/local/lib/hermes-agent/venv/bin/python server.py
Restart=on-failure
```
The `.env` write is write-gated (project `.env`); a shell heredoc redirect to it
also trips the gate — write it via the file tool or a `python -c` `pathlib.write_text`
after arming the gate with the user's greenlight.
