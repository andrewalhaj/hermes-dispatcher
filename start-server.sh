#!/usr/bin/env bash
# Dashboard launch wrapper.
# HARD-PIN HERMES_HOME so a worker's leaked profile env can never
# repoint the dashboard's data routes (kanban.db / memories / references)
# at the wrong tree. Do not rely on inherited env here.
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
cd "$(dirname "$0")" || exit 1
# Source .env so NEO4J_* and other vars are always present regardless of
# which shell invokes this script. Without this, NEO4J_USERNAME falls back
# to the literal "neo4j" and Aura rejects auth — use the instance-specific
# username from the Aura console.
set -a; [ -f .env ] && . ./.env; set +a
# Launch through server.py's __main__ entrypoint (NOT the bare `uvicorn`
# CLI) so the graceful EADDRINUSE / port-conflict handling runs: it probes
# the socket, retries with backoff, optionally falls back to another port,
# and exits with a clear message instead of an unhandled Errno 98 crash.
# Tunables: HERMES_DISPATCHER_{PORT,BIND_RETRIES,BIND_BACKOFF,FALLBACK_PORTS}.
exec ./.venv/bin/python server.py
