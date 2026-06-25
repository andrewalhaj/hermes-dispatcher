# Three different "Hermes WebUIs" — and which ones need config migration

On a Hermes host the phrase "the web dashboard" / "the WebUI" can mean THREE
architecturally different things. They have very different config-parity stories,
and conflating them produces wrong migration advice. Confirm which one the user
means before answering "do I have to move my configs over."

## The three

1. **Built-in `hermes dashboard`** (shipped with hermes-agent, v0.16+).
   - Launch: `hermes dashboard --host 0.0.0.0 --port 9119 --no-open`
     (default port 9119, default bind 127.0.0.1; `--insecure` to bind non-localhost).
   - Needs the `web` + `pty` extras: `pip install 'hermes-agent[web,pty]'`
     (FastAPI/Uvicorn for the server, `ptyprocess` for the embedded TUI). Check with
     `python3 -c "import fastapi, uvicorn, ptyprocess; print('ok')"`.
   - **Chat tab runs the REAL `hermes` TUI behind a pseudo-terminal** — it is NOT a
     reimplementation, not a subprocess-wrapper-with-injected-globals. It spawns the
     same CLI the user runs in a terminal, scoped to a profile's `HERMES_HOME`.
   - **CONFIG PARITY: total, zero migration.** Because it IS the CLI, every per-turn
     mechanism loads identically to Telegram: MEMORY.md, USER.md, SOUL.md, AGENTS.md +
     context files, ALL `~/.hermes/patches/*` guards (write gate, delegation/kanban/
     skill/memory checkpoints — they inject at Python startup, same process class),
     skills, honcho, Supabase/b-full RAG, the same `config.yaml` + model. Nothing to
     transfer. The ONLY thing that doesn't carry is live session HISTORY — the Chat tab
     starts a fresh terminal session per profile (by design, like opening a new CLI
     window), and gateway processes / per-profile session DBs / cron stay per-profile.
   - Machine-level: one server manages every profile; a sidebar profile switcher
     (URL `?profile=<name>`) repoints Config/Keys/Skills/MCP/Models/Chat. `--isolated`
     opts into a per-profile server instead.
   - Docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/web-dashboard

2. **Official `nesquena/hermes-webui`** (`/root/projects/hermes-webui`, upstream repo).
   - Instantiates `AIAgent` **in-process** (`from run_agent import AIAgent` in
     `api/streaming.py`) — a proper embedded agent, NOT a subprocess.
   - CONFIG PARITY: PARTIAL. HERMES_HOME-sourced things load (MEMORY/USER/SOUL/skills/
     honcho/kanban) because the shared `agent/system_prompt.py` reads them. But several
     per-turn features need explicit wiring and have KNOWN gaps (documented in
     `gateway-parity-and-restore.md`): b-full auto-RAG not called, AGENTS.md lost via the
     `TERMINAL_CWD`→workspace cwd trap, session auto-restore client bugs. Patches that
     rely on `sitecustomize.py` injection only apply if that repo's process runs through
     the same startup path. So "switch to upstream" IS a migration with real parity work.

3. **Custom DC-standalone** (`/root/projects/hermes-webui-new`, OUR build — the rest of
   this skill is mostly about this one).
   - Chat tab shells out to `hermes chat -Q --source webui --resume <sid>` as a
     **subprocess** (`asyncio.create_subprocess_exec` in `server.py`, ~line 3182).
   - CONFIG PARITY for the agent run: effectively full, because the subprocess IS the
     CLI (same patches/memory/skills/AGENTS.md as Telegram). But the DASHBOARD PANELS
     (Overview/Galaxy/Insights/etc.) are hand-built and read `~/.hermes` files directly,
     so panel data is its own wiring surface (the populate-phase references cover that).

## The decision shortcut

- User wants the official feature set with our design and our LAYOUT differs from
  upstream → port-into-our-layout (see `port-features-into-our-layout.md`) or
  adopt-upstream (see `adopt-official-upstream.md`).
- User just wants a working browser UI that behaves EXACTLY like their Telegram agent
  with no config moving → **the built-in `hermes dashboard` is the answer, full stop.**
  Don't propose the upstream repo or the custom standalone for this — they both add a
  parity surface the built-in dashboard doesn't have. State the "zero migration except
  session history" fact and offer to wire it up.

## Fronting it on a domain (Cloudflare token-tunnel hosts)

When the tunnel is a `cloudflared` **token** connector (ExecStart runs
`cloudflared tunnel … run --token "$(cat /etc/cloudflared/token)"`, and there's NO
local `config.yml` — only `/etc/cloudflared/token*`), the public-hostname → local-port
mapping lives in the **Cloudflare Zero Trust dashboard**, not on disk. You CANNOT
retarget the hostname from the host. Split the work honestly:
- Agent side (you can do, gated): write a `hermes-dashboard.service` systemd unit running
  `hermes dashboard --host 127.0.0.1 --port 9119 --no-open`, start + verify on 9119.
- Cloudflare side (user must do): Zero Trust → Tunnels → the tunnel → Public Hostnames →
  point `hermes.andrewskingdom.com` at `http://localhost:9119`.
Decide whether to stop/disable the old `hermes-webui.service` (frees 8787) or leave it
running so the custom standalone stays reachable on its own port.
