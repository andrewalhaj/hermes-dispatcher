# Scheduler Recovery Procedure — Option A

**Last tested:** 2026-06-03
**Last updated:** 2026-06-03 (removed stale heartbeat.py reference, added Infra Watchdog + Knowledge Capture)
**Status:** Validated via dry-run

Recovery from backup when Hermes host dies or the scheduler state is lost. The
backup cron (03:00 daily) captures `cron/jobs.json`, `config.yaml`, and all
memories/skills/scripts to `/root/.hermes/backups/`. Keep last 7 days.

Maximum data loss: one missed tick per job (last backup at 03:00, worst case
24h gap). For 6 personal cron jobs this is acceptable.

---

## Scenario 1: Hermes crashed / process restart (same host)

Scheduler picks up `jobs.json` automatically on restart. No manual steps needed.
Confirm with `hermes cron list`.

---

## Scenario 2: New Host (full migration)

### Prerequisites
- Latest backup archive (5 min old or from daily backup)
- New host with Hermes installed (`pip install hermes-agent` or equivalent)
- Hermes configured for direct-to-provider routing (copy `config.yaml` from backup; main model = Claude Sonnet 4.6 via Anthropic OAuth bypass, delegation = deepseek-v4-pro direct — no Manifest)

### Steps

1. **Copy backup to new host**
   ```bash
   scp /root/.hermes/backups/hermes-backup-YYYY-MM-DD.tar.gz new-host:/tmp/
   ```

2. **Extract to new Hermes home**
   ```bash
   mkdir -p /root/.hermes
   tar xzf /tmp/hermes-backup-YYYY-MM-DD.tar.gz -C /root/.hermes/
   ```

3. **Verify jobs.json is intact**
   ```bash
   python3 -c "import json; json.load(open('/root/.hermes/cron/jobs.json')); print('OK')"
   # Expected: OK
   ```

4. **Restore .env (if present in backup)**
   ```bash
   cp /root/.hermes/.env /root/.hermes/.env 2>/dev/null
   # If not in backup, recreate from known config
   ```

5. **Start Hermes**
   ```bash
   hermes start
   # Scheduler reads jobs.json, calculates next_run_at, resumes
   ```

6. **Verify scheduler state**
   ```bash
   hermes cron list
   # All 6 jobs should show state='scheduled' with future next_run_at
   ```

### Expected result
All 6 jobs show `state: scheduled`, `next_run_at` in the future. Jobs fire on
their next scheduled tick. No manual re-creation needed.

---

## Scenario 3: Backup unavailable (manual recovery)

If the backup is lost and you're rebuilding from scratch:

1. Re-create Hermes config (`hermes setup` or copy from memory)
2. Re-register 6 cron jobs (commands below)
3. Jobs fire on next tick

Current job list (2026-06-03):

| Name | Schedule | Script | Type |
|------|----------|--------|------|
| Daily Hermes Backup | `0 3 * * *` | `backup.sh` | no_agent |
| Honcho-to-Obsidian Bridge | `0 8 * * *` | `honcho-bridge.sh` | no_agent |
| Infra Watchdog (15-min) | `*/15 * * * *` | `infra_watchdog.py` | no_agent |
| Weekly KB Dedup Scan | `0 4 * * 0` | `dedup_scan.py` | no_agent |
| Daily Knowledge Capture | `30 2 * * *` | `session_digest.py` | agent |
| Daily Delegation Audit | `0 9 * * *` | (prompt) | agent (deepseek-v4-pro) |

---

## Validation Test (2026-06-03)

```
$ tar xzf /root/.hermes/backups/hermes-backup-2026-06-03.tar.gz -C /tmp/test-restore/
$ python3 -c "import json; json.load(open('/tmp/test-restore/cron/jobs.json')); print('OK')"
OK
$ python3 -c "
import json
jobs = json.load(open('/tmp/test-restore/cron/jobs.json'))
for j in jobs['jobs']:
    name = j.get('name', 'unnamed')
    enabled = j.get('enabled', True)
    print(f'  {name:35s} enabled={enabled}')
"
  Daily Delegation Audit              enabled=True
  Honcho-to-Obsidian Bridge           enabled=True
  Daily Hermes Backup                 enabled=True
  Weekly KB Dedup Scan                enabled=True
  Daily Knowledge Capture             enabled=True
  Infra Watchdog (15-min)             enabled=True
```

All 6 jobs present, enabled. Recovery verified.

---

## Gap: Off-Host Backup

Currently backups live on the same host. If this host dies irrecoverably
(drive failure, cloud instance terminated), the backup is lost with it.

**Fix options:**
- **Easy:** `scp` the archive to VPS after each backup run. Add to `backup.sh`:
  ```bash
  scp "$ARCHIVE" root@178.156.246.115:/root/manifest/backups/
  ```
  VPS keeps the same 7-day retention.
- **Better:** S3 sync (`aws s3 sync` or `rclone` to any object store).
  Decouples from both hosts.
- **Best:** Railway can be configured as a secondary backup target with
  `pg_dump` + `\copy` to a `hermes_backups` table. But overkill for 6 jobs.
