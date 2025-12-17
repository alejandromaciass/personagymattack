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

echo "Starting AgentBeats controller on 127.0.0.1:${CONTROLLER_INTERNAL_PORT} ..."
PORT="${CONTROLLER_INTERNAL_PORT}" HOST="127.0.0.1" agentbeats run_ctrl &

echo "Starting public proxy on 0.0.0.0:${PORT:-8080} ..."
exec python agentbeats/controller_proxy.py
