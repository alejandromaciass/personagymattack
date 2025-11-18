#!/bin/bash
# Start script for PersonaGym-R Green Agent

echo "🚀 Starting PersonaGym-R Green Agent..."
echo "   Environment: Production"
echo "   Port: ${PORT:-8000}"
echo "   Working Directory: $(pwd)"
echo "   Python Version: $(python --version)"
echo "   Available files: $(ls -la)"

# Ensure we're in the right directory
cd "$(dirname "$0")"

# Check if the green agent file exists
if [ ! -f "agentbeats/green_agent.py" ]; then
    echo "❌ Error: agentbeats/green_agent.py not found"
    echo "   Current directory: $(pwd)"
    echo "   Contents: $(ls -la)"
    exit 1
fi

echo "✅ Found green agent file"

# Run the green agent
echo "🎯 Starting green agent..."
exec python agentbeats/green_agent.py