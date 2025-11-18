#!/bin/bash
# AgentBeats run.sh - Launches the PersonaGym-R green agent
# This script is called by the AgentBeats controller (earthshaker)

# The controller sets these environment variables:
# - $HOST: Host to bind to (default: 0.0.0.0)
# - $AGENT_PORT: Port to listen on (default: 8000)

# Set defaults if not provided
export HOST=${HOST:-0.0.0.0}
export AGENT_PORT=${AGENT_PORT:-8000}
export PERSONAGYM_TASKS_DIR=${PERSONAGYM_TASKS_DIR:-tasks}

echo "🚀 Starting PersonaGym-R Green Agent..."
echo "   Host: $HOST"
echo "   Port: $AGENT_PORT"
echo "   Tasks: $PERSONAGYM_TASKS_DIR"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "   Using virtual environment: .venv"
    source .venv/bin/activate
fi

# Run the FastAPI-based green agent
python agentbeats/green_agent.py
