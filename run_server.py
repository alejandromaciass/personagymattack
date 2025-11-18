#!/usr/bin/env python3
"""
Production server startup script for PersonaGym-R Green Agent
"""
import os
import sys
import subprocess

def main():
    print("🚀 PersonaGym-R Production Server")
    print("=================================")
    print(f"Python version: {sys.version}")
    print(f"Working directory: {os.getcwd()}")
    print(f"PORT: {os.getenv('PORT', '8000')}")
    
    # Change to script directory to ensure relative imports work
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    print(f"Changed to directory: {os.getcwd()}")
    print(f"Files in directory: {os.listdir('.')}")
    
    # Check if green agent exists
    green_agent_path = "agentbeats/green_agent.py"
    if not os.path.exists(green_agent_path):
        print(f"❌ ERROR: {green_agent_path} not found!")
        print(f"Available files: {os.listdir('.')}")
        if os.path.exists('agentbeats'):
            print(f"agentbeats directory contents: {os.listdir('agentbeats')}")
        sys.exit(1)
    
    print(f"✅ Found {green_agent_path}")
    
    # Run the green agent
    print("🎯 Starting green agent...")
    try:
        # Use subprocess to run the green agent
        result = subprocess.run([sys.executable, green_agent_path], check=False)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        sys.exit(0)
    except Exception as e:
        print(f"❌ ERROR: Failed to start green agent: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()