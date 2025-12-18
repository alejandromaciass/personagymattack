#!/usr/bin/env bash
set -euo pipefail

# Railway entrypoint.
#
# AgentBeats "Deploy Type: remote" expects a controller-style deployment:
# - `GET /agents` returns agent IDs
# - Per-agent routing happens under `/to_agent/<id>/...`
#
# Therefore, by default we run the earthshaker controller + public proxy for
# both green and white roles. If you explicitly want a direct (non-controller)
# white agent, set `WHITE_RUN_MODE=direct`.

APP_DIR="${APP_DIR:-/app}"
cd "$APP_DIR" || cd "$(dirname "$0")"

AGENT_ROLE_RAW="${AGENT_ROLE:-green}"
# Normalize to avoid common configuration mistakes (e.g., "white.", " White ").
AGENT_ROLE_NORM="$(printf '%s' "$AGENT_ROLE_RAW" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]' | tr -cd '[:alnum:]_-')"

WHITE_RUN_MODE_RAW="${WHITE_RUN_MODE:-controller}"
WHITE_RUN_MODE_NORM="$(printf '%s' "$WHITE_RUN_MODE_RAW" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]' | tr -cd '[:alnum:]_-')"

echo "AGENT_ROLE(raw)=${AGENT_ROLE_RAW} AGENT_ROLE(norm)=${AGENT_ROLE_NORM} WHITE_RUN_MODE(raw)=${WHITE_RUN_MODE_RAW} WHITE_RUN_MODE(norm)=${WHITE_RUN_MODE_NORM}"

if [ "$AGENT_ROLE_NORM" = "white" ] && [ "$WHITE_RUN_MODE_NORM" = "direct" ]; then
  PUBLIC_PORT="${PORT:-8080}"
  export HOST="${HOST:-0.0.0.0}"
  export PORT="$PUBLIC_PORT"

  echo "Starting white agent directly on ${HOST}:${PORT} (WHITE_RUN_MODE=direct) ..."
  exec python agentbeats/white_agent.py
fi

echo "Starting controller+proxy stack (AGENT_ROLE=${AGENT_ROLE_NORM}) ..."
exec bash start_controller_railway.sh
