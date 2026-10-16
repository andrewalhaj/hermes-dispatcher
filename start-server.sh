#!/usr/bin/env bash
# Dashboard launch wrapper.
# HARD-PIN HERMES_HOME so a worker's leaked profile env can never
# repoint the dashboard's data routes (kanban.db / memories / references)
# at the wrong tree. Do not rely on inherited env here.
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$(dirname "$0")" || exit 1
# Source .env so secrets are always present regardless of which shell
# invokes this script.
set -a; [ -f .env ] && . ./.env; set +a
# Launch through server.py's __main__ entrypoint (NOT the bare `uvicorn`
# CLI) so .env variables are available when uvicorn starts.
# Tunables: HERMES_DISPATCHER_{HOST,PORT}.
exec ./.venv/bin/python server.py
