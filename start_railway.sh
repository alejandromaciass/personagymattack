#!/usr/bin/env bash
set -euo pipefail

# Railway entrypoint.
# - Green service: run earthshaker controller + public proxy (remote-controller mode)
# - White service: run the white agent directly (participant-agent mode)

APP_DIR="${APP_DIR:-/app}"
cd "$APP_DIR" || cd "$(dirname "$0")"

AGENT_ROLE_RAW="${AGENT_ROLE:-green}"
# Normalize to avoid common configuration mistakes (e.g., "white.", " White ").
AGENT_ROLE_NORM="$(printf '%s' "$AGENT_ROLE_RAW" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]' | tr -cd '[:alnum:]_-')"

echo "AGENT_ROLE(raw)=${AGENT_ROLE_RAW} AGENT_ROLE(norm)=${AGENT_ROLE_NORM}"

if [ "$AGENT_ROLE_NORM" = "white" ]; then
  PUBLIC_PORT="${PORT:-8080}"
  export HOST="${HOST:-0.0.0.0}"
  export PORT="$PUBLIC_PORT"

  echo "Starting white agent directly on ${HOST}:${PORT} ..."
  exec python agentbeats/white_agent.py
fi

echo "Starting controller+proxy stack (AGENT_ROLE=${AGENT_ROLE_NORM}) ..."
exec bash start_controller_railway.sh
