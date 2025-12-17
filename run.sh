#!/bin/bash
# AgentBeats run.sh - Launches an agent under the AgentBeats controller (earthshaker)

# The controller sets these environment variables:
# - $HOST: Host to bind to (default: 0.0.0.0)
# - $AGENT_PORT: Port to listen on (default: 8000)

# Which agent to run.
# Use AGENT_ROLE=green (default) or AGENT_ROLE=white.
export AGENT_ROLE=${AGENT_ROLE:-green}

# Under the controller, the agent is contacted locally; bind to loopback by default.
export HOST=${HOST:-127.0.0.1}
export AGENT_PORT=${AGENT_PORT:-8000}
export PERSONAGYM_TASKS_DIR=${PERSONAGYM_TASKS_DIR:-tasks}

if [ "$AGENT_ROLE" = "white" ]; then
    AGENT_ENTRYPOINT="agentbeats/white_agent.py"
    AGENT_LABEL="PersonaGymAttack White Agent"
else
    AGENT_ENTRYPOINT="agentbeats/green_agent.py"
    AGENT_LABEL="PersonaGym-R Green Agent"
fi

echo "🚀 Starting $AGENT_LABEL..."
echo "   Host: $HOST"
echo "   Port: $AGENT_PORT"
if [ "$AGENT_ROLE" != "white" ]; then
    echo "   Tasks: $PERSONAGYM_TASKS_DIR"
fi

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    echo "   Using virtual environment: .venv"
    source .venv/bin/activate
fi

exec python "$AGENT_ENTRYPOINT"
