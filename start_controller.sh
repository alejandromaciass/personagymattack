#!/bin/bash
# Start script for AgentBeats earthshaker controller on Railway

echo "🚀 Starting PersonaGym-R AgentBeats Controller..."
echo "   Environment: Railway Cloud"
echo "   Port: ${PORT:-8000}"
echo "   Working Directory: $(pwd)"
echo "   Python Version: $(python --version)"

# Ensure we're in the right directory
cd "$(dirname "$0")"

# Railway sets PORT, but agentbeats controller might use different variables
export CONTROLLER_PORT=${PORT:-8000}
export CONTROLLER_HOST=${HOST:-0.0.0.0}

echo "✅ Starting earthshaker controller on $CONTROLLER_HOST:$CONTROLLER_PORT"

# Run the AgentBeats controller
# The controller will automatically launch our green agent via run.sh
exec agentbeats run_ctrl