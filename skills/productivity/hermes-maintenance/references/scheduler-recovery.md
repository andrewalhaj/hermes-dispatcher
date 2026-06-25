# Scheduler Recovery — Option A: Documented Recovery

## State File

Scheduler state lives in `~/.hermes/cron/jobs.json` (~5KB). Contains every job's schedule, last run time, last status, next run time, and delivery targets.

## Backup Coverage

The daily 03:00 backup (`backup.sh`) includes `cron/` directory. At most 24 hours of scheduler state is unprotected — the database of record is `jobs.json`, not the execution history.

## Recovery Procedure

If the Hermes host is lost or the scheduler stops:

### 1. Restore the state file

```bash
# From the latest daily backup:
tar xzf /root/.hermes/backups/hermes-backup-YYYY-MM-DD.tar.gz -C /tmp/hermes-restore
cp /tmp/hermes-restore/cron/jobs.json /root/.hermes/cron/jobs.json

# Or if restoring to a new host:
scp /root/.hermes/backups/hermes-backup-YYYY-MM-DD.tar.gz user@new-host:/tmp/
ssh user@new-host 'tar xzf /tmp/hermes-backup-*.tar.gz -C /tmp/hermes-restore'
```

### 2. Start Hermes

```bash
hermes gateway start
# Scheduler reads jobs.json, picks up next_run_at, resumes
```

### 3. Verify

```bash
hermes cron list --all
# All jobs should show next_run_at in the future
```

## Expected Data Loss

- At most **one missed tick** per cron job — the tick that was due between the last backup and the outage.
- `no_agent` jobs (backup, dedup, heartbeat, watchdog) cost zero tokens — missed tick means zero cost.
- The one LLM job (Delegation Audit at 09:00) may skip a day. It self-corrects on next run (scans last 24 hours regardless).

## Recovery Time

Under 2 minutes from backup file to running scheduler.

## Test the Recovery (Dry Run)

```bash
# Create a test profile with a copy of the scheduler:
hermes profile create scheduler-test --clone-all
# Verify jobs load:
hermes --profile scheduler-test cron list --all
# Delete test profile after:
hermes profile delete scheduler-test
```

## Gaps This Doesn't Cover

- **Multi-Hermes HA**: Only one Hermes instance runs cron. No leader election.
- **Automatic failover**: Recovery is manual — restore backup, restart.
- **Real-time replication**: The 24-hour backup gap means a crash at 02:59 loses a full day of scheduler state. Acceptable at current scale (5 jobs, 4 of which are no_agent/zero-cost).
