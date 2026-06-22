#!/usr/bin/env bash
# Dashboard launch wrapper.
# HARD-PIN HERMES_HOME so a worker's leaked profile env can never
# repoint the dashboard's data routes (kanban.db / memories / references)
# at the wrong tree. Do not rely on inherited env here.
export HERMES_HOME=/root/.hermes
cd /root/hermes-dispatcher || exit 1
exec ./.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8787 --log-level warning
