"""
PersonaGym-R Green Agent for AgentBeats Platform

This module implements an A2A-compliant green agent that orchestrates
persona adherence testing on the AgentBeats platform.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import traceback
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Import PersonaGym-R components
import sys
import os
from urllib.parse import urlparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.personagym_r.orchestrator import load_task, run_dialog
from src.personagym_r.api_schema import PersonaCard, Goal, Rubric, SeedCfg, Score, TraceEvent
from src.personagym_r.tools import io_bus

# A2A Protocol Models
class AgentCard(BaseModel):
    """Agent self-description following A2A protocol."""
    name: str = "PersonaGym-R Green Agent"
    version: str = "1.0.0"
    description: str = "Adversarial persona adherence benchmark for AI agents"
    capabilities: List[str] = [
        "persona_testing",
        "adversarial_evaluation",
        "break_detection",
        "safety_scoring"
    ]
    agent_type: str = "green"  # This is a hosting/evaluator agent
    protocol_version: str = "A2A-1.0"
    url: str = ""


def _public_base_url(request: Request | None = None) -> str:
    """Best-effort public base URL.

    Priority:
    1) AGENT_URL (set by controller; should include /to_agent/<id>)
    2) Forwarded headers (x-forwarded-proto/host)
    3) HOST/PORT
    """
    env_agent_url = os.getenv("AGENT_URL")
    if env_agent_url:
        parsed = urlparse(env_agent_url)
        path = (parsed.path or "").rstrip("/")
        hostname = (parsed.hostname or "").lower()

        internal_hosts = {"0.0.0.0", "127.0.0.1", "localhost"}
        if request is not None and hostname in internal_hosts:
            xf_proto = request.headers.get("x-forwarded-proto")
            xf_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
            if xf_host:
                scheme = xf_proto or "http"
                return f"{scheme}://{xf_host}{path}".rstrip("/")

        return env_agent_url.rstrip("/")

    if request is not None:
        xf_proto = request.headers.get("x-forwarded-proto")
        xf_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        if xf_host:
            scheme = xf_proto or "http"
            return f"{scheme}://{xf_host}".rstrip("/")

    host = os.getenv("HOST", "127.0.0.1")
    port = os.getenv("PORT") or os.getenv("AGENT_PORT") or "8000"
    scheme = "http"
    return f"{scheme}://{host}:{port}".rstrip("/")
    
class TaskRequest(BaseModel):
    """Task assignment from AgentBeats platform."""
    task_id: str
    task_type: str
    participant_agents: List[str]  # URLs of white agents to test
    config: Dict[str, Any]  # Task-specific configuration
    timeout_seconds: Optional[int] = 300

class TaskResponse(BaseModel):
    """Response to task assignment."""
    task_id: str
    status: str  # "accepted", "rejected"
    estimated_duration_seconds: Optional[int] = None
    message: Optional[str] = None

class MetricResult(BaseModel):
    """Individual metric result."""
    name: str
    value: float
    description: str

class AssessmentResult(BaseModel):
    """Complete assessment results for a participant."""
    agent_url: str
    task_id: str
    metrics: List[MetricResult]
    success: bool
    error_message: Optional[str] = None
    execution_time_seconds: float
    metadata: Dict[str, Any] = {}

class StatusUpdate(BaseModel):
    """Progress update during assessment."""
    task_id: str
    status: str  # "running", "completed", "failed"
    progress_percent: int
    message: str
    results: Optional[List[AssessmentResult]] = None


# A2A-Compliant White Agent Client
class A2AWhiteAgentClient:
    """Client for interacting with A2A-compliant white agents."""
    
    def __init__(self, agent_url: str, persona: PersonaCard):
        self.agent_url = agent_url
        self.persona = persona
        self.session_id = None
        
    async def initialize_session(self):
        """Initialize a new session with the white agent."""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.agent_url}/a2a/session",
                json={"persona": self.persona.model_dump()}
            )
            response.raise_for_status()
            self.session_id = response.json()["session_id"]
    
    def respond(self, observation: Dict[str, Any]) -> str:
        """Get response from white agent (synchronous wrapper)."""
        import httpx
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.agent_url}/a2a/respond",
                json={
                    "session_id": self.session_id,
                    "observation": observation
                }
            )
            response.raise_for_status()
            return response.json()["response"]
    
    def submit(self) -> str:
        """Get final submission from white agent."""
        import httpx
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{self.agent_url}/a2a/submit",
                json={"session_id": self.session_id}
            )
            response.raise_for_status()
            return response.json()["final_response"]
    
    async def reset(self):
        """Reset the white agent for a new assessment."""
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.agent_url}/a2a/reset"
            )
            response.raise_for_status()


# Green Agent Implementation
class PersonaGymGreenAgent:
    """Green agent orchestrating PersonaGym-R evaluations."""
    
    def __init__(self, tasks_dir: str = "tasks"):
        self.tasks_dir = Path(tasks_dir)
        self.active_tasks: Dict[str, Dict] = {}
        self.logger = logging.getLogger("PersonaGymGreenAgent")
        
    def get_agent_card(self) -> AgentCard:
        """Return agent card per A2A protocol."""
        return AgentCard(url=_public_base_url())
    
    def list_available_tasks(self) -> List[Dict[str, str]]:
        """List all available assessment tasks."""
        tasks = []
        if self.tasks_dir.exists():
            for task_path in self.tasks_dir.iterdir():
                if task_path.is_dir():
                    tasks.append({
                        "task_id": task_path.name,
                        "name": task_path.name.replace("_", " ").title(),
                        "description": f"Persona adherence test: {task_path.name}"
                    })
        return tasks
    
    async def accept_task(self, task_request: TaskRequest) -> TaskResponse:
        """Accept and validate a task request."""
        # Validate that the task exists
        task_path = self.tasks_dir / task_request.task_id
        if not task_path.exists():
            return TaskResponse(
                task_id=task_request.task_id,
                status="rejected",
                message=f"Task {task_request.task_id} not found"
            )
        
        # Validate that we have participant agents
        if not task_request.participant_agents:
            return TaskResponse(
                task_id=task_request.task_id,
                status="rejected",
                message="No participant agents specified"
            )
        
        # Store task info
        self.active_tasks[task_request.task_id] = {
            "request": task_request,
            "status": "accepted",
            "start_time": datetime.now()
        }
        
        return TaskResponse(
            task_id=task_request.task_id,
            status="accepted",
            estimated_duration_seconds=60 * len(task_request.participant_agents),
            message=f"Will test {len(task_request.participant_agents)} agent(s)"
        )
    
    async def run_assessment(self, task_request: TaskRequest) -> List[AssessmentResult]:
        """Run the assessment on participant agents."""
        results = []
        task_path = self.tasks_dir / task_request.task_id
        
        # Load task configuration
        persona_data, goal, rubric, seed = load_task(task_path)
        
        # Override seed if provided in config
        if "seed" in task_request.config:
            seed.rng_seed = task_request.config["seed"]
        
        # Test each participant agent
        for agent_url in task_request.participant_agents:
            start_time = datetime.now()
            
            try:
                # Create A2A client for the white agent
                white_agent = A2AWhiteAgentClient(agent_url, persona_data)
                
                # Reset the agent before testing
                await white_agent.reset()
                
                # Initialize session
                await white_agent.initialize_session()
                
                # Run the dialog evaluation
                score, trace = run_dialog(white_agent, persona_data, goal, rubric, seed)
                
                # Convert to AgentBeats metrics
                metrics = [
                    MetricResult(
                        name="persona_adherence",
                        value=score.P,
                        description="How well the agent maintained the persona"
                    ),
                    MetricResult(
                        name="break_resistance",
                        value=score.B,
                        description="Resistance to adversarial attacks"
                    ),
                    MetricResult(
                        name="safety",
                        value=score.S,
                        description="Safety score (PII, harmful content)"
                    ),
                    MetricResult(
                        name="efficiency",
                        value=score.E,
                        description="Task completion efficiency"
                    ),
                    MetricResult(
                        name="overall_score",
                        value=score.R,
                        description="Weighted overall rating (PBSE)"
                    )
                ]
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                results.append(AssessmentResult(
                    agent_url=agent_url,
                    task_id=task_request.task_id,
                    metrics=metrics,
                    success=True,
                    execution_time_seconds=execution_time,
                    metadata={
                        "turns": score.turns,
                        "broke": score.broke,
                        "break_severity": score.break_severity,
                        "break_turn": score.break_turn,
                        "reason": score.reason
                    }
                ))
                
            except Exception as e:
                self.logger.error(f"Error testing agent {agent_url}: {e}")
                execution_time = (datetime.now() - start_time).total_seconds()
                
                results.append(AssessmentResult(
                    agent_url=agent_url,
                    task_id=task_request.task_id,
                    metrics=[],
                    success=False,
                    error_message=str(e),
                    execution_time_seconds=execution_time
                ))
        
        return results


# FastAPI Application
app = FastAPI(
    title="PersonaGym-R Green Agent",
    description="A2A-compliant green agent for persona adherence testing",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# Add CORS middleware for AgentBeats platform
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to AgentBeats domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    if os.getenv("REQUEST_DEBUG", "0") not in {"1", "true", "True"}:
        return await call_next(request)

    import sys
    from datetime import datetime as dt
    
    start_time = dt.now()
    
    # Log incoming request with distinctive formatting
    print(f"\n{'─'*70}", file=sys.stderr)
    print(f"📥 INCOMING REQUEST [{start_time.isoformat()}]", file=sys.stderr)
    print(f"{'─'*70}", file=sys.stderr)
    print(f"Method: {request.method}", file=sys.stderr)
    print(f"URL: {request.url}", file=sys.stderr)
    print(f"Path: {request.url.path}", file=sys.stderr)
    print(f"Query: {request.url.query}", file=sys.stderr)
    print(f"Headers:", file=sys.stderr)
    for key, value in request.headers.items():
        print(f"  {key}: {value}", file=sys.stderr)
    
    # Try to log body for POST requests
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body = await request.body()
            if body:
                print(f"Body: {body.decode(errors='replace')}", file=sys.stderr)
            else:
                print(f"Body: (empty)", file=sys.stderr)
        except Exception as e:
            print(f"Body: (could not read - {e})", file=sys.stderr)
    
    # Process request
    try:
        response = await call_next(request)
    except Exception as e:
        print(f"❌ ERROR processing request: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise
    
    # Log response
    end_time = dt.now()
    duration = (end_time - start_time).total_seconds()
    print(f"{'─'*70}", file=sys.stderr)
    print(f"📤 OUTGOING RESPONSE [{end_time.isoformat()}]", file=sys.stderr)
    print(f"{'─'*70}", file=sys.stderr)
    print(f"Status Code: {response.status_code}", file=sys.stderr)
    print(f"Duration: {duration:.3f}s", file=sys.stderr)
    print(f"Response Headers:", file=sys.stderr)
    for key, value in response.headers.items():
        print(f"  {key}: {value}", file=sys.stderr)
    print(f"{'─'*70}\n", file=sys.stderr)
    
    return response

# Initialize green agent
green_agent = PersonaGymGreenAgent(tasks_dir="tasks")


def _maybe_mark_controller_state_running() -> None:
    agent_url = os.getenv("AGENT_URL")
    if not agent_url:
        return

    # Expecting something like: https://<host>/to_agent/<id>
    parts = agent_url.rstrip("/").split("/")
    try:
        idx = parts.index("to_agent")
        agent_id = parts[idx + 1]
    except Exception:
        return

    try:
        state_path = Path(".ab") / "agents" / agent_id / "state"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("running", encoding="utf-8")
    except Exception:
        # Never fail startup due to best-effort state marking.
        return


@app.on_event("startup")
async def _startup_mark_running():
    _maybe_mark_controller_state_running()


@app.get("/healthz")
async def healthz():
    """Lightweight health endpoint for proxies/controllers."""
    return {"ok": True}

@app.get("/")
async def root():
    """Root endpoint redirecting to agent card."""
    return {
        "message": "PersonaGym-R Green Agent",
        "agent_card": "/.well-known/agent-card.json",
        "health": "/health",
        "tasks": "/a2a/tasks",
        "documentation": "/docs",
        "api_info": "/api"
    }

@app.get("/api")
async def api_info():
    """API information and endpoint listing."""
    return {
        "name": "PersonaGym-R Green Agent API",
        "version": "1.0.0",
        "protocol": "A2A-1.0",
        "agent_type": "green",
        "endpoints": {
            "discovery": {
                "agent_card": "GET /.well-known/agent-card.json",
                "a2a_card": "GET /a2a/card",
                "health": "GET /health",
                "status": "GET /status"
            },
            "tasks": {
                "list_tasks": "GET /a2a/tasks",
                "accept_task": "POST /a2a/task",
                "run_assessment": "POST /a2a/run"
            },
            "launcher": {
                "start": "POST /launcher/start",
                "stop": "POST /launcher/stop", 
                "status": "GET /launcher/status"
            },
            "options": {
                "cors_preflight": "OPTIONS /a2a/*"
            }
        }
    }

@app.get("/a2a/card")
async def get_card():
    """Return agent card (A2A protocol)."""
    return green_agent.get_agent_card()

@app.get("/agent-card")
async def get_simple_agent_card():
    """Alternative simple agent card endpoint."""
    return {
        "name": "PersonaGym-R Green Agent",
        "version": "1.0.0",
        "agent_type": "green",
        "protocol_version": "A2A-1.0"
    }

@app.post("/api/agents/card")
async def agentbeats_get_agent_card(request: Request):
    """AgentBeats-specific agent card endpoint."""
    try:
        # Try to get the request body if present
        try:
            body = await request.json()
        except:
            body = {}
            
        card = green_agent.get_agent_card()
        return {
            "success": True,
            "agent_card": {
                "name": card.name,
                "version": card.version,
                "description": card.description,
                "capabilities": card.capabilities,
                "agent_type": card.agent_type,
                "protocol_version": card.protocol_version,
                "url": card.url,
                "endpoints": {
                    "agent_card": "/a2a/card",
                    "list_tasks": "/a2a/tasks",
                    "accept_task": "/a2a/task",
                    "run_assessment": "/a2a/run",
                    "health_check": "/health",
                    "launcher_start": "/launcher/start",
                    "launcher_stop": "/launcher/stop",
                    "launcher_status": "/launcher/status"
                }
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/agents/card") 
async def agentbeats_get_agent_card_get():
    """AgentBeats-specific agent card endpoint (GET version)."""
    card = green_agent.get_agent_card()
    return {
        "success": True,
        "agent_card": {
            "name": card.name,
            "version": card.version,
            "description": card.description,
            "capabilities": card.capabilities,
            "agent_type": card.agent_type,
            "protocol_version": card.protocol_version,
            "url": card.url
        }
    }

@app.options("/api/agents/card")
async def agentbeats_agent_card_options():
    """CORS preflight for AgentBeats agent card endpoint."""
    return {}

@app.post("/api/agents/validate")
async def agentbeats_validate_agent():
    """AgentBeats agent validation endpoint."""
    return {
        "success": True,
        "valid": True,
        "agent_type": "green",
        "protocol_version": "A2A-1.0",
        "message": "Agent validation successful"
    }

# IMPORTANT: Put specific endpoints BEFORE catchall routes
@app.get("/.well-known/agent-card.json")
async def get_agent_card_standard(request: Request):
    """Standard AgentBeats agent card endpoint with detailed logging."""
    import sys
    from datetime import datetime
    card = green_agent.get_agent_card()
    public_url = _public_base_url(request)
    # Log request details for debugging
    print("\n=== AGENT CARD ENDPOINT HIT ===", file=sys.stderr)
    print(f"[{datetime.now().isoformat()}] {request.method} {request.url}", file=sys.stderr)
    print(f"Headers: {dict(request.headers)}", file=sys.stderr)
    try:
        body = await request.body()
        if body:
            print(f"Body: {body.decode(errors='replace')}", file=sys.stderr)
    except Exception as e:
        print(f"(Could not read body: {e})", file=sys.stderr)
    print("=== END AGENT CARD LOG ===\n", file=sys.stderr)
    return {
        "name": card.name,
        "version": card.version,
        "description": card.description,
        "capabilities": card.capabilities,
        "agent_type": card.agent_type,
        "protocol_version": card.protocol_version,
        "url": public_url,
        "endpoints": {
            "agent_card": "/a2a/card",
            "list_tasks": "/a2a/tasks",
            "accept_task": "/a2a/task", 
            "run_assessment": "/a2a/run",
            "health_check": "/health",
            "launcher_start": "/launcher/start",
            "launcher_stop": "/launcher/stop", 
            "launcher_status": "/launcher/status"
        },
        "contact": {
            "repository": "https://github.com/alejandromaciass/personagymattack",
            "maintainer": "PersonaGym-R Team"
        },
        "requirements": {
            "min_agents": 1,
            "max_agents": 10,
            "supported_protocols": ["A2A-1.0"],
            "resource_requirements": {
                "memory_mb": 512,
                "cpu_cores": 2,
                "gpu": False
            }
        },
        "metadata": {
            "created": "2025-11-18",
            "tags": ["persona-testing", "adversarial-evaluation", "safety", "benchmark"],
            "difficulty": "medium-hard",
            "estimated_duration_minutes": 5,
            "launcher_url": f"{public_url}/launcher/start"
        }
    }


@app.head("/.well-known/agent-card.json")
async def head_agent_card():
    """HEAD handler for agent card to support clients that probe with HEAD."""
    # Return headers only (no body) but report JSON content-type so callers know
    return Response(status_code=200, headers={"content-type": "application/json"})

@app.options("/a2a/card")
async def options_card():
    """Handle CORS preflight for agent card."""
    return {}

@app.get("/a2a/tasks")
async def list_tasks():
    """List available assessment tasks."""
    return {"tasks": green_agent.list_available_tasks()}

@app.options("/a2a/tasks")
async def options_tasks():
    """Handle CORS preflight for tasks."""
    return {}

@app.post("/a2a/task")
async def accept_task(task_request: TaskRequest) -> TaskResponse:
    """Accept a new task assignment."""
    return await green_agent.accept_task(task_request)

@app.get("/a2a/task")
async def get_task_info():
    """Get information about task acceptance endpoint."""
    return {
        "endpoint": "/a2a/task",
        "method": "POST",
        "description": "Accept a new task assignment",
        "accepts": "TaskRequest",
        "returns": "TaskResponse"
    }

@app.post("/a2a/run")
async def run_task(task_request: TaskRequest) -> StatusUpdate:
    """Execute an assessment task."""
    # First accept the task
    acceptance = await green_agent.accept_task(task_request)
    
    if acceptance.status == "rejected":
        return StatusUpdate(
            task_id=task_request.task_id,
            status="failed",
            progress_percent=0,
            message=acceptance.message or "Task rejected"
        )
    
    # Run the assessment
    try:
        results = await green_agent.run_assessment(task_request)
        
        return StatusUpdate(
            task_id=task_request.task_id,
            status="completed",
            progress_percent=100,
            message=f"Tested {len(results)} agent(s)",
            results=results
        )
    except Exception as e:
        return StatusUpdate(
            task_id=task_request.task_id,
            status="failed",
            progress_percent=0,
            message=f"Assessment failed: {str(e)}"
        )

@app.get("/a2a/run")
async def get_run_info():
    """Get information about assessment execution endpoint."""
    return {
        "endpoint": "/a2a/run",
        "method": "POST",
        "description": "Execute an assessment task",
        "accepts": "TaskRequest",
        "returns": "StatusUpdate"
    }

@app.options("/a2a/run")
async def options_run():
    """Handle CORS preflight for run."""
    return {}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "agent_type": "green", "version": "1.0.0"}

@app.get("/status")
async def status_check():
    """Alternative status endpoint."""
    return {"status": "online", "agent_type": "green", "version": "1.0.0", "ready": True}

@app.get("/debug")
async def debug_endpoint():
    """Debug endpoint to check if requests are being logged."""
    return {
        "message": "Debug endpoint working",
        "timestamp": datetime.now().isoformat(),
        "note": "Check server logs for incoming request logs from AgentBeats"
    }


@app.get("/diagnostics")
async def diagnostics(request: Request):
    """Diagnostics for AgentBeats integration.

    Shows how we compute the public base URL and what the platform likely sees.
    """
    public_url = _public_base_url(request)
    return {
        "computed_public_url": public_url,
        "computed_agent_card_url": f"{public_url}/.well-known/agent-card.json",
        "env": {
            "HOST": os.getenv("HOST"),
            "PORT": os.getenv("PORT"),
            "AGENT_PORT": os.getenv("AGENT_PORT"),
            "AGENT_URL": os.getenv("AGENT_URL"),
        },
        "forwarded": {
            "x-forwarded-proto": request.headers.get("x-forwarded-proto"),
            "x-forwarded-host": request.headers.get("x-forwarded-host"),
            "host": request.headers.get("host"),
        },
        "paths": {
            "status": "/status",
            "health": "/health",
            "agent_card": "/.well-known/agent-card.json",
        },
    }

@app.post("/launcher/start")
async def launcher_start():
    """Launcher endpoint to start the agent."""
    base_url = _public_base_url()
    return {
        "status": "started",
        "message": "PersonaGym-R Green Agent is running",
        "agent_url": base_url,
        "endpoints": {
            "agent_card": "/a2a/card",
            "tasks": "/a2a/tasks",
            "run": "/a2a/run",
            "health": "/health"
        }
    }

@app.get("/launcher/start")
async def launcher_start_get():
    """Launcher endpoint info (GET version)."""
    return {
        "endpoint": "/launcher/start",
        "method": "POST",
        "description": "Start the PersonaGym-R Green Agent",
        "returns": "Launcher status and agent URL"
    }

@app.post("/launcher/stop") 
async def launcher_stop():
    """Launcher endpoint to stop the agent."""
    return {
        "status": "stopped",
        "message": "PersonaGym-R Green Agent stop requested"
    }

@app.get("/launcher/stop")
async def launcher_stop_get():
    """Launcher stop endpoint info (GET version)."""
    return {
        "endpoint": "/launcher/stop",
        "method": "POST", 
        "description": "Stop the PersonaGym-R Green Agent",
        "returns": "Stop confirmation"
    }

@app.get("/launcher/status")
async def launcher_status():
    """Launcher status check."""
    base_url = _public_base_url()
    return {
        "status": "running",
        "agent_type": "green",
        "version": "1.0.0",
        "agent_url": base_url,
        "uptime": "online"
    }

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get configuration from environment (set by Railway/other cloud providers)
    import os
    host = os.getenv('HOST', '127.0.0.1')
    # Under the controller, AGENT_PORT is the bind port. PORT is typically the controller's port.
    port = int(os.getenv('AGENT_PORT', os.getenv('PORT', '8000')))
    agent_url = os.getenv('AGENT_URL', f'http://{host}:{port}')
    
    print("\n" + "="*60)
    print("🚀 PERSONAGYM-R GREEN AGENT STARTING")
    print("="*60)
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Agent URL: {agent_url}")
    print(f"Environment variables:")
    print(f"  - HOST: {os.getenv('HOST', 'NOT SET')}")
    print(f"  - PORT: {os.getenv('PORT', 'NOT SET')}")
    print(f"  - AGENT_PORT: {os.getenv('AGENT_PORT', 'NOT SET')}")
    print(f"  - AGENT_URL: {os.getenv('AGENT_URL', 'NOT SET')}")
    print("\nKey endpoints:")
    print(f"  - Agent card: {agent_url}/.well-known/agent-card.json")
    print(f"  - Health: {agent_url}/health")
    print(f"  - Status: {agent_url}/status")
    print("="*60 + "\n")
    
    # Run the server
    uvicorn.run(app, host=host, port=port)
