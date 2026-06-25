# Gateway Self-Protection: Restart Workaround

The Hermes gateway process blocks `systemctl restart` and `docker compose restart` from within the gateway — SIGTERM would kill the gateway mid-command.

## Workaround: Cronjob with no_agent=true

Create a one-shot bash script and schedule it via cronjob:

```bash
# 1. Write restart script to ~/.hermes/scripts/
cat > ~/.hermes/scripts/restart_services.sh << 'EOF'
#!/bin/bash
systemctl restart hermes-dashboard
cd /root/web-stack/firecrawl && docker compose restart api
echo "Services restarted"
EOF

# 2. Schedule via no_agent cron (runs script directly, no LLM)
# The cronjob scheduler runs outside the gateway process — not blocked.
hermes cron create \
  --script restart_services.sh \
  --no-agent \
  --schedule "now" \
  --deliver local
```

## When this bites
- After modifying `server.py` or `routes/*.py` — need dashboard restart
- After modifying `docker-compose.yml` — need container restart
- Any config change that requires service reload

## Alternative: Manual
Give Andrew the commands and let them run from a separate terminal:
```bash
systemctl restart hermes-dashboard
docker compose restart <service>
```
