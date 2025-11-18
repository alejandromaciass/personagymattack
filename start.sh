#!/bin/bash
# Start script for PersonaGym-R Green Agent

echo "🚀 Starting PersonaGym-R Green Agent..."
echo "   Environment: Production"
echo "   Port: ${PORT:-8000}"

# Run the green agent
exec python agentbeats/green_agent.py