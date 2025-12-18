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


@app.get("/.well-known/agent-card.json")
async def root_agent_card(request: Request) -> Response:
    """Return an agent card at the controller root.

    We resolve the first discovered agent and return its agent card.
    """
    base = _controller_base_url()

    async with httpx.AsyncClient(timeout=15.0) as client:
        agents_resp = await client.get(f"{base}/agents")
        agents_resp.raise_for_status()
        agents = agents_resp.json() if agents_resp.headers.get("content-type", "").startswith("application/json") else {}

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
        try:
            agents = agents_resp.json()
        except Exception:
            agents = {}
        if not isinstance(agents, dict) or not agents:
            return Response(status_code=503)
    return Response(status_code=200, media_type="application/json")


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_all(request: Request, full_path: str) -> Response:
    """Generic reverse proxy to the internal controller."""
    base = _controller_base_url()
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
