import asyncio

import httpx


def _rpc_payload(text: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "m1",
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            }
        },
    }


def test_green_jsonrpc_post_root():
    from agentbeats.green_agent import app

    async def _run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/", json=_rpc_payload("hello"))

    resp = asyncio.run(_run())

    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "1"
    assert data["result"]["kind"] == "message"


def test_white_jsonrpc_post_root():
    from agentbeats.white_agent import app

    async def _run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/", json=_rpc_payload("hello white"))

    resp = asyncio.run(_run())

    assert resp.status_code == 200
    data = resp.json()
    assert data["jsonrpc"] == "2.0"
    assert data["id"] == "1"
    assert data["result"]["kind"] == "message"


def test_tau_style_agent_cards_present():
    from agentbeats.green_agent import app as green_app
    from agentbeats.white_agent import app as white_app

    for app in (green_app, white_app):
        async def _run() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                return await client.get("/.well-known/agent-card.json")

        resp = asyncio.run(_run())
        assert resp.status_code == 200
        card = resp.json()
        # tau-style keys used by assessment runner / AgentBeats checks
        assert "protocolVersion" in card
        assert "preferredTransport" in card
        assert "capabilities" in card and isinstance(card["capabilities"], dict)
        assert "url" in card
