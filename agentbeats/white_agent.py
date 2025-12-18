"""PersonaGymAttack White Agent (Participant)

This is a minimal A2A-compliant "white" agent implementation that can be
submitted as a participant agent on AgentBeats.

It supports:
- Session lifecycle: /a2a/session, /a2a/reset
- Interaction: /a2a/respond
- Finalization: /a2a/submit

The agent is intentionally simple and deterministic. It keeps session state
in-memory (sufficient for typical AgentBeats checks and demos).
"""

from __future__ import annotations

import logging
import os
import uuid
from urllib.parse import urlparse
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import uvicorn


logger = logging.getLogger("PersonaGymAttackWhiteAgent")


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

        # If the controller injected an internal URL (common in PaaS), prefer
        # forwarded headers to reconstruct the public URL while preserving the
        # /to_agent/<id> path.
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
    return f"http://{host}:{port}".rstrip("/")


class AgentCard(BaseModel):
    name: str = "PersonaGymAttack White Agent"
    version: str = "1.0.0"
    description: str = "A2A white/participant agent for PersonaGymAttack demos"
    capabilities: list[str] = ["a2a_chat", "participant"]
    agent_type: str = "white"
    protocol_version: str = "A2A-1.0"
    url: str = ""
    endpoints: Dict[str, str] = Field(default_factory=dict)


class CreateSessionRequest(BaseModel):
    persona: Dict[str, Any] = Field(default_factory=dict)


class CreateSessionResponse(BaseModel):
    session_id: str


class RespondRequest(BaseModel):
    session_id: str
    observation: Dict[str, Any] = Field(default_factory=dict)


class RespondResponse(BaseModel):
    response: str


class SubmitRequest(BaseModel):
    session_id: str


class SubmitResponse(BaseModel):
    final_response: str


@dataclass
class SessionState:
    persona: Dict[str, Any]
    created_at: str
    last_response: str = ""


class WhiteAgent:
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionState] = {}

    def create_session(self, persona: Dict[str, Any]) -> str:
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = SessionState(
            persona=persona,
            created_at=datetime.utcnow().isoformat() + "Z",
        )
        return session_id

    def get_session(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            raise KeyError(session_id)
        return self._sessions[session_id]

    def respond(self, session_id: str, observation: Dict[str, Any]) -> str:
        state = self.get_session(session_id)

        # Extract a user message if present.
        user_text = None
        if isinstance(observation, dict):
            user_text = observation.get("message") or observation.get("input")
            if user_text is None and isinstance(observation.get("messages"), list) and observation["messages"]:
                last = observation["messages"][-1]
                if isinstance(last, dict):
                    user_text = last.get("content")

        user_text = user_text if isinstance(user_text, str) and user_text.strip() else "(no user message)"

        persona_name = None
        if isinstance(state.persona, dict):
            persona_name = state.persona.get("name") or state.persona.get("persona_name")

        prefix = f"[{persona_name}] " if isinstance(persona_name, str) and persona_name else ""
        response = f"{prefix}I received: {user_text}"

        state.last_response = response
        return response

    def submit(self, session_id: str) -> str:
        state = self.get_session(session_id)
        return state.last_response or "(no response yet)"

    def reset(self) -> None:
        self._sessions.clear()


app = FastAPI(
    title="PersonaGymAttack White Agent",
    description="A2A white/participant agent",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


white_agent = WhiteAgent()


@app.get("/")
async def root() -> Dict[str, Any]:
    """Root endpoint with quick links.

    The green agent exposes a small JSON index at `/`. Some clients (and humans)
    probe the base URL (e.g., `/to_agent/<id>`) before fetching the agent card.
    Returning a 200 here improves compatibility.
    """
    return {
        "message": "PersonaGymAttack White Agent",
        "agent_card": "/.well-known/agent-card.json",
        "health": "/health",
        "tasks": "/a2a/tasks",
        "documentation": "/docs",
        "api_info": "/api",
    }


@app.get("/api")
async def api_info() -> Dict[str, Any]:
    return {
        "name": "PersonaGymAttack White Agent API",
        "version": "1.0.0",
        "protocol": "A2A-1.0",
        "agent_type": "white",
        "endpoints": {
            "discovery": {
                "agent_card": "GET /.well-known/agent-card.json",
                "a2a_card": "GET /a2a/card",
                "health": "GET /health",
                "status": "GET /status",
            },
            "a2a": {
                "session": "POST /a2a/session",
                "respond": "POST /a2a/respond",
                "submit": "POST /a2a/submit",
                "reset": "POST /a2a/reset",
            },
        },
    }


@app.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "healthy", "agent_type": "white", "version": "1.0.0"}


@app.get("/status")
async def status() -> Dict[str, Any]:
    return {"status": "online", "agent_type": "white", "version": "1.0.0", "ready": True}


@app.get("/.well-known/agent-card.json")
async def agent_card(request: Request) -> Dict[str, Any]:
    base = _public_base_url(request)
    card = AgentCard(
        url=base,
        endpoints={
            "session": "/a2a/session",
            "respond": "/a2a/respond",
            "submit": "/a2a/submit",
            "reset": "/a2a/reset",
            "healthz": "/healthz",
            "health": "/health",
            "status": "/status",
        },
    )
    return card.model_dump()


@app.head("/.well-known/agent-card.json")
async def head_agent_card() -> Response:
    return Response(status_code=200, headers={"content-type": "application/json"})


@app.get("/a2a/card")
async def a2a_card(request: Request) -> Dict[str, Any]:
    return await agent_card(request)


@app.post("/a2a/session", response_model=CreateSessionResponse)
async def create_session(payload: CreateSessionRequest) -> CreateSessionResponse:
    session_id = white_agent.create_session(payload.persona)
    return CreateSessionResponse(session_id=session_id)


@app.post("/a2a/respond", response_model=RespondResponse)
async def respond(payload: RespondRequest) -> RespondResponse:
    try:
        text = white_agent.respond(payload.session_id, payload.observation)
        return RespondResponse(response=text)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown session_id")


@app.post("/a2a/submit", response_model=SubmitResponse)
async def submit(payload: SubmitRequest) -> SubmitResponse:
    try:
        final = white_agent.submit(payload.session_id)
        return SubmitResponse(final_response=final)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown session_id")


@app.post("/a2a/reset")
async def reset() -> Dict[str, Any]:
    white_agent.reset()
    return {"ok": True}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Under controller, bind to loopback and use AGENT_PORT.
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("AGENT_PORT", os.getenv("PORT", "8000")))

    uvicorn.run(app, host=host, port=port)
