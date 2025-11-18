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
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Import PersonaGym-R components
import sys
import os
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
        return AgentCard()
    
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
    version="1.0.0"
)

# Add CORS middleware for AgentBeats platform
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to AgentBeats domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize green agent
green_agent = PersonaGymGreenAgent(tasks_dir="tasks")

@app.get("/")
async def root():
    """Root endpoint redirecting to agent card."""
    return {
        "message": "PersonaGym-R Green Agent",
        "agent_card": "/.well-known/agent-card.json",
        "health": "/health",
        "tasks": "/a2a/tasks"
    }

@app.get("/a2a/card")
async def get_card():
    """Return agent card (A2A protocol)."""
    return green_agent.get_agent_card()

@app.get("/a2a/tasks")
async def list_tasks():
    """List available assessment tasks."""
    return {"tasks": green_agent.list_available_tasks()}

@app.post("/a2a/task")
async def accept_task(task_request: TaskRequest) -> TaskResponse:
    """Accept a new task assignment."""
    return await green_agent.accept_task(task_request)

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

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "agent_type": "green", "version": "1.0.0"}

@app.get("/.well-known/agent-card.json")
async def get_agent_card_standard():
    """Standard AgentBeats agent card endpoint."""
    card = green_agent.get_agent_card()
    return {
        "name": card.name,
        "version": card.version,
        "description": card.description,
        "capabilities": card.capabilities,
        "agent_type": card.agent_type,
        "protocol_version": card.protocol_version,
        "endpoints": {
            "agent_card": "/a2a/card",
            "list_tasks": "/a2a/tasks",
            "accept_task": "/a2a/task", 
            "run_assessment": "/a2a/run",
            "health_check": "/health"
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
            "estimated_duration_minutes": 5
        }
    }


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Get configuration from environment (set by Railway/other cloud providers)
    import os
    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', os.getenv('AGENT_PORT', '8000')))  # Railway uses PORT, earthshaker uses AGENT_PORT
    
    # Run the server
    uvicorn.run(app, host=host, port=port)
