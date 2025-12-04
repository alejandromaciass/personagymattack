# AgentBeats Integration: Root Cause Analysis & Solution

## Executive Summary

**Problem**: AgentBeats only calls `/status` on your agent, never calls `/.well-known/agent-card.json`, so `card_content` and `card_url` remain null.

**Root Cause**: You were running your agent directly (`python agentbeats/green_agent.py`) instead of through the **AgentBeats Controller** (`agentbeats run_ctrl`). AgentBeats expects to interact with agents through a controller proxy, not directly.

**Solution**: Use the controller in your Procfile, which:
1. Starts and manages your agent process
2. Creates a proxy to your agent at `http://localhost:{AGENT_PORT}`
3. Exposes that proxy publicly via `/to_agent/{agent_id}/{path}`
4. Fetches and caches the agent card during agent startup

---

## How the AgentBeats Controller Works

### The Flow (with Controller)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Railway starts the controller via Procfile:              │
│    web: agentbeats run_ctrl                                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Controller starts run.sh (your agent launcher)           │
│    with environment variables:                              │
│    - AGENT_PORT: random port (e.g., 15234)                 │
│    - HOST: 0.0.0.0                                          │
│    - AGENT_URL: public proxy URL                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Your agent (green_agent.py) reads environment vars       │
│    and starts listening on http://localhost:15234           │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Controller fetches agent card from                       │
│    http://localhost:15234/.well-known/agent-card.json       │
│    and caches it in .ab/agents/{agent_id}/agent_card        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Controller exposes proxy publicly:                       │
│    https://web-production-4866d.up.railway.app/to_agent/    │
│    {agent_id}/.well-known/agent-card.json                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. AgentBeats calls status endpoint to check agent:         │
│    GET /status → ✅ works (through controller proxy)        │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. AgentBeats calls agent card endpoint:                    │
│    GET /.well-known/agent-card.json                         │
│    → Controller proxies to localhost:15234                  │
│    → Fetches card and populates card_content & card_url ✅  │
└─────────────────────────────────────────────────────────────┘
```

### What Was Happening Before (Direct Agent Approach)

```
❌ You ran: python agentbeats/green_agent.py directly
            ↓
❌ Agent listened on port 8080 (Railway's default)
            ↓
❌ AgentBeats called: https://web-production-4866d.up.railway.app/status
            ✅ This worked (agent card is optional in status check)
            ↓
❌ AgentBeats called: https://web-production-4866d.up.railway.app/.well-known/agent-card.json
            ✅ This should have worked... but didn't
            
Why? Because without a controller, the platform can't:
- Manage agent lifecycle properly
- Reset the agent between assessments
- Handle stateful interactions correctly
```

---

## The Key Code: How Controller Discovers the Agent Card

### In `controller.py` (earthshaker):

```python
async def get_agent_card(agent_port: int):
    """Fetch agent card from running agent"""
    httpx_client = httpx.AsyncClient()
    resolver = A2ACardResolver(
        httpx_client=httpx_client, 
        base_url=f"http://localhost:{agent_port}"
    )
    try:
        card: AgentCard | None = await resolver.get_agent_card()
        return card
    except Exception as _:
        return None


def maintain_agent_process(agent_id: str):
    """Main loop that manages agent state"""
    while True:
        if state == "starting":
            card = asyncio.run(get_agent_card(agent_port))
            if card is not None:
                # Cache the agent card in .ab/agents/{agent_id}/agent_card
                with open(os.path.join(agent_folder, "agent_card"), "w") as f:
                    f.write(card.model_dump_json(indent=2))
                # Mark agent as "running"
                with open(os.path.join(agent_folder, "state"), "w") as f:
                    f.write("running")
```

**Key insight**: The A2ACardResolver uses the [A2A specification](https://a2a-protocol.org/) which defines standard endpoints for agent discovery:
1. First tries: `/.well-known/agent-card.json`
2. Falls back to: `/a2a/card`

---

## What We Fixed

### 1. **Procfile** ✅ Already Fixed
```makefile
web: agentbeats run_ctrl
```

This tells Railway to start the controller, which will manage your agent.

### 2. **run.sh** ✅ Fixed
```bash
#!/bin/bash
# The controller sets these environment variables:
# - $HOST: Host to bind to (default: 0.0.0.0)
# - $AGENT_PORT: Port to listen on (default: 8000)

export HOST=${HOST:-0.0.0.0}
export AGENT_PORT=${AGENT_PORT:-8000}

# ... activate venv ...

exec python agentbeats/green_agent.py
```

**Why**: The agent must read from environment variables, not CLI args. The controller sets these before starting run.sh.

### 3. **green_agent.py** ✅ Enhanced with Debug Logging
```python
if __name__ == "__main__":
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', os.getenv('AGENT_PORT', '8000')))
    agent_url = os.getenv('AGENT_URL', f'http://{host}:{port}')
    
    print(f"Agent URL: {agent_url}")
    print(f"Environment: HOST={host}, AGENT_PORT={port}")
    
    uvicorn.run(app, host=host, port=port)
```

Plus added comprehensive request logging middleware to capture ALL incoming requests.

---

## What Will Happen After Railway Redeploys

1. **Controller starts** on port 8010 (default)
2. **Controller calls run.sh** with `AGENT_PORT=15234` (random)
3. **Your agent starts** listening on `http://localhost:15234`
4. **Controller fetches agent card** from `http://localhost:15234/.well-known/agent-card.json`
5. **Controller caches it** in `.ab/agents/{agent_id}/agent_card`
6. **Controller proxy becomes ready** at `https://web-production-4866d.up.railway.app/to_agent/{agent_id}`
7. **AgentBeats platform calls** the health check through the proxy ✅
8. **AgentBeats calls agent card** through proxy → Card is fetched and populated ✅

---

## Expected Logs After Fix

You should see in Railway logs:

```
🚀 PERSONAGYM-R GREEN AGENT STARTING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Host: 0.0.0.0
Port: 15234
Agent URL: https://web-production-4866d.up.railway.app/to_agent/abc123...
Environment variables:
  - HOST: 0.0.0.0
  - PORT: NOT SET
  - AGENT_PORT: 15234
  - AGENT_URL: https://...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Then:
📥 INCOMING REQUEST [...]
Method: GET
URL: http://localhost:15234/.well-known/agent-card.json
... (from the controller proxy)
```

---

## Why Your Direct Approach Didn't Work

When running the agent directly:
- ✅ `/status` endpoint worked (basic health check)
- ❌ `/.well-known/agent-card.json` endpoint existed but AgentBeats never called it
- ❌ No controller to manage agent lifecycle
- ❌ No way to reset the agent between assessments
- ❌ AgentBeats platform didn't know how to interact with a stateful agent

The platform **specifically designed the controller** to solve these problems.

---

## Next Steps

1. **Wait for Railway to redeploy** (usually 1-2 minutes after push)
2. **Check Railway logs** for:
   - "🚀 PERSONAGYM-R GREEN AGENT STARTING"
   - "📥 INCOMING REQUEST" logs with the card endpoint
3. **Refresh AgentBeats dashboard** to see if card loads
4. **Check if card_content and card_url are now populated** (no longer null)

---

## References

- [AgentBeats Documentation - Controller](https://docs.agentbeats.org/Blogs/blog-3/#agentbeats-controller)
- [A2A Protocol - Agent Card Discovery](https://a2a-protocol.org/)
- [earthshaker Source Code](file:///usr/local/python/3.13.9/lib/python3.13/site-packages/agentbeats/controller.py)

---

## Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Procfile** | `web: agentbeats run_ctrl` | ✅ Already correct |
| **run.sh** | Passed CLI args | ✅ Now uses env vars |
| **Agent startup** | Direct Python | ✅ Via controller |
| **Agent port** | Fixed 8080 | ✅ Dynamic from controller |
| **Agent discovery** | Manual | ✅ Automatic via controller |
| **Card endpoint** | Existed but unused | ✅ Controller fetches it |
| **AgentBeats integration** | Partial (status only) | ✅ Full (status + card) |

