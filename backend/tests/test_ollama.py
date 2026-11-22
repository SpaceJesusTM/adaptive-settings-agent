from __future__ import annotations

import asyncio
from dataclasses import replace

import httpx
import pytest

from app.agent.health import probe_ollama


@pytest.mark.parametrize(("case", "message"), [
    ("offline", "Cannot reach Ollama"),
    ("timeout", "timed out"),
    ("missing", "missing from this Ollama"),
    ("bad_json", "malformed status data"),
    ("bad_shape", "malformed status data"),
    ("bad_details", "malformed status data"),
    ("unreadable_model", "HTTP 500"),
    ("ready", "Connected to the local model"),
])
def test_ollama_status(settings, monkeypatch, case, message):
    def handler(request):
        match request.url.path:
            case "/api/version":
                if case == "offline":
                    raise httpx.ConnectError("offline", request=request)
                if case == "timeout":
                    raise httpx.ReadTimeout("timeout", request=request)
                return httpx.Response(200, json={"version": "test"})
            case "/api/tags":
                if case == "bad_json":
                    return httpx.Response(200, content=b"not JSON")
                if case == "bad_shape":
                    return httpx.Response(200, json={"models": [None]})
                names = [] if case == "missing" else [{"model": settings.ollama_model}]
                return httpx.Response(200, json={"models": names})
            case "/api/show":
                if case == "unreadable_model":
                    return httpx.Response(500)
                if case == "bad_details":
                    return httpx.Response(200, json={"details": {"family": {"bad": "field"}}})
                return httpx.Response(200, json={"details": {"quantization_level": "Q4_K_M"}, "capabilities": ["tools"]})
        pytest.fail(f"Unexpected request to {request.url.path}")

    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs))
    result = asyncio.run(probe_ollama(settings, force=True))
    assert result["state"] == ("connected" if case == "ready" else "unavailable")
    assert message in result["message"]
    if case == "ready":
        assert result["details"]["quantization"] == "Q4_K_M"
        assert result["capabilities"] == ["tools"]
    else:
        assert result["details"] is None


def test_no_model_configured_skips_network(settings, monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_: pytest.fail("Unexpected Ollama request"))
    result = asyncio.run(probe_ollama(replace(settings, ollama_model=""), force=True))
    assert result["state"] == "not_configured"
