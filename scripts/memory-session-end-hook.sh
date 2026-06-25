#!/usr/bin/env bash
# memory-session-end-hook.sh — on_session_end hook for memory offload.
#
# Fires when a conversation ends. Reads and discards the JSON payload from
# stdin (contains session_id), then spawns session-end-offload.py in the
# background so gateway teardown is not blocked.
#
# The Python script handles its own threshold check — it exits silently if
# MEMORY.md is below 85%. No gateway restart needed after editing; the hook
# is re-read from config.yaml on each gateway startup.

# Consume stdin payload (don't fail if stdin is empty)
read -r -d '' _payload 2>/dev/null || true

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
VENV_PY="/usr/local/lib/hermes-agent/venv/bin/python3"
SCRIPT="$HERMES_HOME/scripts/session-end-offload.py"

# Background — gateway does not wait
(
  export HERMES_HOME
  exec "$VENV_PY" "$SCRIPT" </dev/null >/dev/null 2>&1
) &

exit 0
