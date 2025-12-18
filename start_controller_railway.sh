#!/usr/bin/env bash
set -euo pipefail

# Ensure we run from the repo root in Railway (typically /app).
APP_DIR="${APP_DIR:-/app}"
cd "$APP_DIR"

# The AgentBeats controller stores agent state under .ab/agents.
# In some PaaS setups, the initial working directory may differ; make this explicit.
mkdir -p .ab/agents

# Run the upstream controller on an internal port so we can expose a small
# proxy on the public PORT that also serves /.well-known/agent-card.json.
export CONTROLLER_INTERNAL_PORT=${CONTROLLER_INTERNAL_PORT:-8081}
export CONTROLLER_INTERNAL_HOST=${CONTROLLER_INTERNAL_HOST:-127.0.0.1}

PUBLIC_PORT=${PORT:-8080}

echo "Starting AgentBeats controller on ${CONTROLLER_INTERNAL_HOST}:${CONTROLLER_INTERNAL_PORT} ..."
# earthshaker's controller honors CONTROLLER_HOST/CONTROLLER_PORT; also set
# HOST/PORT for backward compatibility.
CONTROLLER_HOST="${CONTROLLER_INTERNAL_HOST}" \
CONTROLLER_PORT="${CONTROLLER_INTERNAL_PORT}" \
HOST="${CONTROLLER_INTERNAL_HOST}" \
PORT="${CONTROLLER_INTERNAL_PORT}" \
	agentbeats run_ctrl &

export HOST=${HOST:-0.0.0.0}
export PORT=${PUBLIC_PORT}

echo "Starting public proxy on ${HOST}:${PORT} ..."
exec python agentbeats/controller_proxy.py
