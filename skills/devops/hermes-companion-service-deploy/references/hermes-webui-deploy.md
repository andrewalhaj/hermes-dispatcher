# Hermes WebUI deploy — exact recipe

Repo: `https://github.com/nesquena/hermes-webui` (active, MIT, Python + vanilla JS,
no build step). Default port **8787**. State dir `~/.hermes/webui`. Auto-discovers
the existing Hermes config/venv/models/memory/sessions — zero extra config to start.
Gives full CLI parity in-browser: sessions, profiles, models, skills, cron, workspace
file browser, streaming, tool-call cards, voice, dark theme, mobile layout.

## Proven sequence (verified end-to-end on andrew-Macmini, tailnet 100.113.100.81)

```bash
# 1. clone (new files, no gate)
cd /root/projects && git clone https://github.com/nesquena/hermes-webui.git hermes-webui

# 2. bootstrap to confirm it boots — foreground, WILL time out (= success). Read stdout
#    for "listening on http://0.0.0.0:8787" then move on.
cd /root/projects/hermes-webui && python3 bootstrap.py --no-browser

# 3. free the port the foreground bootstrap is holding
fuser -k 8787/tcp; sleep 1; ss -tlnp | grep 8787 || echo "8787 CLEAR"

# 4. generate password
python3 -c "import secrets,string; print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(24)))"
```

## Two launch options

### Option A — project's ctl.sh daemon (quick, no boot persistence)
```bash
cd /root/projects/hermes-webui && \
  HERMES_WEBUI_HOST=0.0.0.0 HERMES_WEBUI_PORT=8787 HERMES_WEBUI_PASSWORD=<pw> \
  ./ctl.sh start
# ctl.sh status / logs --lines 100 / restart / stop
# PID at ~/.hermes/webui.pid, log at ~/.hermes/webui.log
```
NOTE: env vars passed INLINE — do NOT write `.env` into the repo, the write-gate
blocks any `*/.env` path. ctl.sh stop only kills processes it started itself.

### Option B — systemd unit (preferred for daily driver; auto-start + restart)
Stop ctl.sh / free the port first, then (write-gate must be armed with user greenlight;
`write_file` refuses /etc so use terminal heredoc):
```bash
cat > /etc/systemd/system/hermes-webui.service <<'EOF'
[Unit]
Description=Hermes Web UI
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/projects/hermes-webui
Environment="HERMES_WEBUI_HOST=0.0.0.0"
Environment="HERMES_WEBUI_PORT=8787"
Environment="HERMES_WEBUI_PASSWORD=<pw>"
ExecStart=/usr/local/lib/hermes-agent/venv/bin/python bootstrap.py --no-browser
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable hermes-webui && systemctl start hermes-webui
```
The systemd `ExecStart` runs `bootstrap.py` which internally launches `server.py` under
the agent venv. `Memory ~90MB RSS` steady-state.

## Verify
```bash
curl -sf http://127.0.0.1:8787/health    # {"status":"ok",...}
ss -tlnp | grep 8787                       # LISTEN 0.0.0.0:8787
systemctl status hermes-webui --no-pager   # active (running); enabled
```
Access from any tailnet device: `http://<tailnet-ip>:8787`. First browser open fires
an onboarding wizard that should just confirm the already-detected provider key and
skip — point user to `hermes model` only if provider setup is incomplete.
