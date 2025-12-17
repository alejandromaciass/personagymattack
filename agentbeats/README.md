# AgentBeats Integration

This directory contains all components needed to deploy PersonaGym-R as a **green agent** (hosting/evaluator) on the AgentBeats platform.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (direct)
python agentbeats/green_agent.py

# Run for AgentBeats Remote (controller)
# (recommended/required by AgentBeats v2 Remote)
agentbeats run_ctrl

# Agent will be available at http://localhost:8000
```

## Files

- **`green_agent.py`**: Main A2A-compliant web service implementing the green agent
- **`controller.py`**: State management and reset functionality for assessment isolation
- **`config.yaml`**: Complete configuration including tasks, metrics, and deployment settings
- **`requirements.txt`**: Additional dependencies for A2A protocol (FastAPI, uvicorn, httpx)
- **`__init__.py`**: Package initialization

## What is a Green Agent?

In the AgentBeats ecosystem:

- **Green Agent** = Hosting/Evaluator agent that orchestrates assessments
- **White Agent** = Participant agent being tested/evaluated
- **Attacker** = Adversarial component (part of green agent in PersonaGym-R)

PersonaGym-R is a green agent that tests white agents' ability to maintain assigned personas under adversarial attacks.

## How It Works

1. **AgentBeats Platform** sends a task request to PersonaGym-R green agent
2. **Green Agent** prepares the assessment:
   - Loads task configuration (persona, rubric, attack tactics)
   - Contacts white agent(s) to reset their state
   - Initializes sessions with persona assignments
3. **Assessment Execution**:
   - Green agent (attacker) engages white agent in multi-turn dialog
   - Monitors for persona breaks and safety violations
   - Tracks efficiency and adherence metrics
4. **Scoring**:
   - Computes PBSE metrics (Persona, Break, Safety, Efficiency)
   - Generates detailed results and metadata
5. **Results Reporting**:
   - Returns metrics to AgentBeats platform
   - Updates leaderboards

## A2A Protocol Endpoints

PersonaGym-R green agent implements:

- `GET /a2a/card` - Agent self-description
- `GET /a2a/tasks` - List available assessment tasks
- `POST /a2a/task` - Accept task assignment
- `POST /a2a/run` - Execute assessment
- `POST /a2a/reset` - Reset state
- `GET /health` - Health check

## Configuration

Edit `config.yaml` to customize:

- Available tasks and scenarios
- Metric definitions and weights
- Attack tactics
- Break level definitions
- Deployment settings

## Deployment

See parent directory documentation:

- **`AGENTBEATS_INTEGRATION.md`** - Complete integration guide
- **`AGENTBEATS_SUBMISSION.md`** - Submission instructions
- **`deploy_agentbeats.sh`** - Deployment helper script

### Quick Deployment Options

**Local Testing**:
```bash
python agentbeats/green_agent.py
```

**Docker**:
```bash
docker build -t personagym-green-agent .
docker run -p 8000:8000 personagym-green-agent
```

**Remote Server**:
```bash
# On your server
agentbeats run_ctrl
# Submit Controller URL to AgentBeats: https://your-server.com
# (Do NOT include /to_agent/...; the platform discovers agents via the controller)
```

## White Agent Requirements

To be tested by PersonaGym-R, white agents must implement A2A protocol:

```
POST /a2a/session    - Initialize session with persona
POST /a2a/respond    - Respond to attacker messages
POST /a2a/submit     - Provide final response
POST /a2a/reset      - Reset state
```

See `AGENTBEATS_INTEGRATION.md` for detailed requirements and examples.

## Testing

Test the green agent locally:

```bash
# Terminal 1: Start green agent
python agentbeats/green_agent.py

# Terminal 2: Test endpoints
curl http://localhost:8000/a2a/card
curl http://localhost:8000/a2a/tasks
curl http://localhost:8000/health
curl http://localhost:8000/diagnostics
```

## Metrics

PersonaGym-R evaluates agents on:

- **P** (35%): Persona adherence
- **B** (35%): Break resistance
- **S** (20%): Safety
- **E** (10%): Efficiency
- **R** (100%): Overall score = weighted sum

## Support

Questions? See:
- `AGENTBEATS_INTEGRATION.md` - Comprehensive guide
- `AGENTBEATS_SUBMISSION.md` - Submission checklist
- GitHub Issues: https://github.com/miayen7/personagym/issues
- Email: sec+agentbeats@berkeley.edu
