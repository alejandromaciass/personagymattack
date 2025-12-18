"""Small proxy in front of the AgentBeats controller.

Why this exists:
- The AgentBeats v2 Remote controller exposes discovery at /agents and per-agent
  routing under /to_agent/<id>/...
- Some UI flows attempt to load an agent card from the controller root at
  /.well-known/agent-card.json. The upstream controller may return 404 there,
  which makes the UI display: "Agent Card Content could not be loaded".

This proxy:
- Serves GET /.well-known/agent-card.json by resolving the first discovered
  agent and returning its proxied agent-card JSON.
- Proxies all other HTTP requests to the controller running on
  http://127.0.0.1:<CONTROLLER_INTERNAL_PORT>.

It is intended for PaaS deployments (Railway) where we control the start script.
"""

from __future__ import annotations

import os
import json
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _controller_base_url() -> str:
    port = os.getenv("CONTROLLER_INTERNAL_PORT", "8081")
    host = os.getenv("CONTROLLER_INTERNAL_HOST", "127.0.0.1")
    return f"http://{host}:{port}"


def _filter_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in headers:
        lk = k.lower()
        if lk in HOP_BY_HOP_HEADERS:
            continue
        # Let httpx set content-length.
        if lk == "content-length":
            continue
        out[k] = v
    return out


def _safe_json_bytes_load(content: bytes) -> Any | None:
    """Best-effort JSON loader.

    In the wild we've observed upstream responses that claim
    application/json but contain literal CR/LF characters inside string
    values (invalid JSON). AgentBeats' checker appears to be strict.
    We sanitize common control characters and try again.
    """
    try:
        return json.loads(content)
    except Exception:
        pass

    try:
        text = content.decode("utf-8", errors="replace")
        if "\n" in text or "\r" in text:
            text = text.replace("\r", "").replace("\n", "")
        return json.loads(text)
    except Exception:
        return None


def _safe_response_json(resp: httpx.Response) -> Any | None:
    try:
        return resp.json()
    except Exception:
        return _safe_json_bytes_load(resp.content)


async def _first_agent_id() -> str | None:
    """Return the first discovered agent id, if any."""
    base = _controller_base_url()
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        resp = await client.get(f"{base}/agents")
        if resp.status_code >= 400:
            return None
        agents = _safe_response_json(resp)
        if not isinstance(agents, dict) or not agents:
            return None
        agent_id = next(iter(agents.keys()))
        return agent_id if isinstance(agent_id, str) and agent_id else None


def _looks_like_agent_id(value: str) -> bool:
    if len(value) != 32:
        return False
    try:
        int(value, 16)
        return True
    except Exception:
        return False


app = FastAPI(
    title="AgentBeats Controller Proxy",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root(request: Request) -> Response:
    """Simple root endpoint.

    Some checkers probe the controller root and may not follow redirects.
    Return a small JSON index and include a best-effort agent count.
    """
    base = _controller_base_url()
    agent_count: int | None = None
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            agents_resp = await client.get(f"{base}/agents")
            if agents_resp.status_code < 400:
                agents_json = _safe_response_json(agents_resp)
                if isinstance(agents_json, dict):
                    agent_count = len(agents_json)
    except Exception:
        agent_count = None

    payload = {
        "status": "ok",
        "agent_count": agent_count,
        "agent_card": "/.well-known/agent-card.json",
        "agents": "/agents",
    }
    return Response(
        status_code=200,
        content=json.dumps(payload).encode("utf-8"),
        media_type="application/json",
        headers={"cache-control": "no-store"},
    )


@app.get("/agents")
async def agents(request: Request) -> Response:
    """Proxy /agents but fix up stale 'starting' state.

    The upstream controller may leave an agent in state='starting' even after the
    process is reachable (common in PaaS deployments). Some UI flows display this
    state prominently, so we opportunistically promote 'starting' -> 'running'
    when the agent answers health checks.
    """
    base = _controller_base_url()

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        upstream = await client.get(
            f"{base}/agents",
            params=dict(request.query_params),
            headers=dict(request.headers),
        )

        # If upstream failed or isn't JSON, just pass it through.
        content_type = upstream.headers.get("content-type", "")
        if upstream.status_code >= 400 or not content_type.startswith("application/json"):
            return Response(
                status_code=upstream.status_code,
                content=upstream.content,
                headers=_filter_headers(upstream.headers.items()),
                media_type=content_type or None,
            )

        agents_json = _safe_response_json(upstream)
        if agents_json is None:
            return Response(
                status_code=upstream.status_code,
                content=upstream.content,
                headers=_filter_headers(upstream.headers.items()),
                media_type=content_type,
            )

        if isinstance(agents_json, dict):
            # Best-effort health probe for agents that are still marked 'starting'.
            for agent_id, info in list(agents_json.items()):
                if not isinstance(info, dict):
                    continue
                if info.get("state") != "starting":
                    continue
                try:
                    health = await client.get(f"{base}/to_agent/{agent_id}/health")
                    if health.status_code < 400:
                        info["state"] = "running"
                except Exception:
                    # Leave as-is if health probe fails.
                    pass

        return Response(
            status_code=upstream.status_code,
            content=json.dumps(agents_json).encode("utf-8"),
            headers=_filter_headers(upstream.headers.items()),
            media_type="application/json",
        )


async def _is_known_agent(agent_id: str) -> bool:
    """Return True if agent_id exists in the controller's /agents."""
    base = _controller_base_url()
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        resp = await client.get(f"{base}/agents")
        if resp.status_code >= 400:
            return True  # Don't block if controller is unhappy; proxy normally.
        agents_json = _safe_response_json(resp)
        if agents_json is None:
            return True
        return isinstance(agents_json, dict) and agent_id in agents_json


@app.api_route(
    "/to_agent/{agent_id}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@app.api_route(
    "/to_agent/{agent_id}/{rest:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
async def proxy_to_agent_safe(request: Request, agent_id: str, rest: str = "") -> Response:
    """Proxy /to_agent/* but avoid 500s for stale agent IDs.

    The upstream controller can throw FileNotFoundError for a removed agent id,
    which bubbles up as 500. Some UIs interpret that as "agent card can't be
    loaded" even when a new agent is running.
    """
    try:
        known = await _is_known_agent(agent_id)
    except Exception:
        known = True

    if not known:
        return Response(
            status_code=404,
            content=json.dumps({"detail": "Unknown agent id"}).encode("utf-8"),
            media_type="application/json",
            headers={"cache-control": "no-store"},
        )

    # Proxy through our generic handler.
    full_path = f"to_agent/{agent_id}/{rest}".rstrip("/") if rest else f"to_agent/{agent_id}"
    return await proxy_all(request, full_path)


@app.get("/.well-known/agent-card.json")
async def root_agent_card(request: Request) -> Response:
    """Return an agent card at the controller root.

    We resolve the first discovered agent and return its agent card.
    """
    base = _controller_base_url()

    async with httpx.AsyncClient(timeout=15.0) as client:
        agents_resp = await client.get(f"{base}/agents")
        agents_resp.raise_for_status()
        agents = (
            _safe_response_json(agents_resp)
            if agents_resp.headers.get("content-type", "").startswith("application/json")
            else {}
        )

        if not isinstance(agents, dict) or not agents:
            return Response(status_code=503, content=b"No agents available")

        agent_id = next(iter(agents.keys()))

        # Ask the controller for the proxied agent card.
        # (Also pass forwarded headers; some controllers forward them downstream.)
        public_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
        public_proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        forward_headers = {}
        if public_host:
            forward_headers["x-forwarded-host"] = public_host
        if public_proto:
            forward_headers["x-forwarded-proto"] = public_proto

        card_resp = await client.get(
            f"{base}/to_agent/{agent_id}/.well-known/agent-card.json",
            headers=forward_headers,
        )
        card_resp.raise_for_status()

        # Rewrite the card's public URL if it points at an internal host.
        try:
            card_json: dict[str, Any] = card_resp.json()
            card_url = card_json.get("url")
            if isinstance(card_url, str) and public_host:
                parsed = urlparse(card_url)
                internal_hosts = {"0.0.0.0", "127.0.0.1", "localhost"}
                if (parsed.hostname or "").lower() in internal_hosts:
                    scheme = public_proto or "https"
                    rebuilt = parsed._replace(scheme=scheme, netloc=public_host)
                    card_json["url"] = urlunparse(rebuilt)
            content = json.dumps(card_json).encode("utf-8")
        except Exception:
            content = card_resp.content

        return Response(status_code=200, content=content, media_type="application/json")


@app.head("/.well-known/agent-card.json")
async def root_agent_card_head() -> Response:
    """HEAD support for UI health checks.

    Some clients probe the card URL with HEAD first. We respond 200 if there is
    at least one discovered agent; 503 if the controller has none.
    """
    base = _controller_base_url()
    async with httpx.AsyncClient(timeout=10.0) as client:
        agents_resp = await client.get(f"{base}/agents")
        if agents_resp.status_code >= 400:
            return Response(status_code=agents_resp.status_code)
        agents = _safe_response_json(agents_resp) or {}
        if not isinstance(agents, dict) or not agents:
            return Response(status_code=503)
    return Response(status_code=200, media_type="application/json")


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_all(request: Request, full_path: str) -> Response:
    """Generic reverse proxy to the internal controller."""
    base = _controller_base_url()

    # Some checkers have been observed issuing paths with a missing agent id, e.g.
    # /to_agent//.well-known/agent-card.json or /to_agent/.well-known/agent-card.json.
    # Rewrite these to the first discovered agent.
    if full_path == "to_agent" or full_path == "to_agent/":
        agent_id = await _first_agent_id()
        if not agent_id:
            return Response(status_code=503, content=b"No agents available")
        full_path = f"to_agent/{agent_id}"
    elif full_path.startswith("to_agent/"):
        remainder = full_path.removeprefix("to_agent/")
        first_segment = remainder.split("/", 1)[0]
        if (first_segment == "") or (not _looks_like_agent_id(first_segment)):
            agent_id = await _first_agent_id()
            if not agent_id:
                return Response(status_code=503, content=b"No agents available")
            rest = remainder.lstrip("/")
            full_path = f"to_agent/{agent_id}/{rest}" if rest else f"to_agent/{agent_id}"

    url = f"{base}/{full_path}" if full_path else f"{base}/"

    body = await request.body()
    headers = dict(request.headers)

    # Preserve forwarding headers from the edge -> proxy -> controller.
    # If they are missing, populate them from this request.
    if "x-forwarded-host" not in {k.lower(): v for k, v in headers.items()}:
        host = request.headers.get("host")
        if host:
            headers["x-forwarded-host"] = host
    if "x-forwarded-proto" not in {k.lower(): v for k, v in headers.items()}:
        headers["x-forwarded-proto"] = "https" if request.url.scheme == "https" else "http"

    # Some upstream controllers don't implement HEAD for all endpoints.
    # To keep browser-based UIs happy, translate HEAD -> GET upstream and
    # return an empty body.
    upstream_method = "GET" if request.method.upper() == "HEAD" else request.method

    async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
        upstream = await client.request(
            method=upstream_method,
            url=url,
            params=dict(request.query_params),
            content=body,
            headers=headers,
        )

        content = b"" if request.method.upper() == "HEAD" else upstream.content

        return Response(
            status_code=upstream.status_code,
            content=content,
            headers=_filter_headers(upstream.headers.items()),
            media_type=upstream.headers.get("content-type"),
        )


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host=host, port=port)
