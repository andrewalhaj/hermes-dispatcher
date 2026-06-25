#!/bin/bash
# Daily backup: core Hermes config, memory, skills, scripts, knowledge DB, cron
# Excludes: node/, image_cache/, audio_cache/, profile snapshots (one-off)
set -e
DEST="/root/.hermes/backups"
mkdir -p "$DEST"
TIMESTAMP=$(date +%Y-%m-%d)
ARCHIVE="$DEST/hermes-backup-$TIMESTAMP.tar.gz"

tar czf "$ARCHIVE" \
  --exclude='node' \
  --exclude='image_cache' \
  --exclude='audio_cache' \
  --exclude='profiles/stable-*' \
  --exclude='*.tar.gz' \
  -C /root/.hermes \
  config.yaml \
  memories/ \
  skills/ \
  scripts/ \
  knowledge_db/ \
  cron/ \
  .env 2>/dev/null  # knowledge_db/ now holds only graph.sqlite + benchmark cache (vectors moved to Supabase)

# Keep last 7 daily backups
find "$DEST" -name 'hermes-backup-*.tar.gz' -mtime +7 -delete

# Off-host copy to VPS (non-fatal)
ssh root@178.156.246.115 "mkdir -p /root/manifest/backups && find /root/manifest/backups -name 'hermes-backup-*.tar.gz' -mtime +7 -delete"
scp -q "$ARCHIVE" root@178.156.246.115:/root/manifest/backups/ 2>/dev/null || true

SIZE=$(du -h "$ARCHIVE" | cut -f1)
echo "OK: $ARCHIVE ($SIZE)"
