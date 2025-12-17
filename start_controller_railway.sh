#!/usr/bin/env bash
set -euo pipefail

# Ensure we run from the repo root in Railway (typically /app).
APP_DIR="${APP_DIR:-/app}"
cd "$APP_DIR"

# The AgentBeats controller stores agent state under .ab/agents.
# In some PaaS setups, the initial working directory may differ; make this explicit.
mkdir -p .ab/agents

exec agentbeats run_ctrl
