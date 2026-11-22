"""Shared fixtures: isolated temp database, scripted fake chat model, API client."""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from langchain_core.messages import AIMessage  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services import Services, build_services  # noqa: E402


class FakeChatModel:
    """Minimal stand-in for ChatOllama: scripted plan/compose responses, no network."""

    def __init__(self, *, plan_responses: Optional[list[AIMessage]] = None, compose_payloads: Optional[list[Any]] = None,
                 delay_s: float = 0.0):
        self.plan_responses = list(plan_responses or [])
        self.compose_payloads = list(compose_payloads or [])
        self.delay_s = delay_s
        self.calls: list[str] = []

    # --- tool-calling interface
    def bind_tools(self, _tools: list[Any]) -> "FakeChatModel":
        return self

    async def ainvoke(self, _messages: Any) -> AIMessage:
        self.calls.append("plan")
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        return self.plan_responses.pop(0) if self.plan_responses else AIMessage(content="READY")

    # --- structured output interface
    def with_structured_output(self, schema: Any, method: str = "json_schema", include_raw: bool = False) -> "_Structured":
        return _Structured(self, schema)


class _Structured:
    def __init__(self, model: FakeChatModel, schema: Any):
        self.model, self.schema = model, schema

    async def ainvoke(self, _messages: Any) -> dict[str, Any]:
        self.model.calls.append("compose")
        if self.model.delay_s:
            await asyncio.sleep(self.model.delay_s)
        payload = self.model.compose_payloads.pop(0) if self.model.compose_payloads else {"intent": "other", "reply": "ok"}
        text = payload if isinstance(payload, str) else json.dumps(payload)
        raw = AIMessage(content=text)
        try:
            parsed = self.schema.model_validate_json(text)
            return {"raw": raw, "parsed": parsed, "parsing_error": None}
        except Exception as exc:  # noqa: BLE001
            return {"raw": raw, "parsed": None, "parsing_error": exc}


@pytest.fixture
def fake_model_holder() -> dict[str, FakeChatModel]:
    return {"model": FakeChatModel()}


@pytest.fixture
def settings(tmp_path: Path):
    base = get_settings()
    return replace(base, db_path=tmp_path / "db dir with spaces" / "test.db", backup_dir=tmp_path / "backups",
                   ollama_model="fake-model:test", agent_deadline_s=10.0, store_chat_history=True)


@pytest.fixture
def services(settings, fake_model_holder) -> Services:
    factory: Callable[[Any], tuple[Any, Any]] = lambda _s: (fake_model_holder["model"], fake_model_holder["model"])
    return build_services(settings, model_factory=factory)


@pytest.fixture
def client(services):
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app(services)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def connected_ollama(monkeypatch):
    """Pretend the configured model is installed so the AI path (with the fake model) is exercised."""
    from app.agent import runner as runner_mod

    async def fake_probe(settings, *, force: bool = False):
        return {"state": "connected", "model": settings.ollama_model, "baseUrl": settings.ollama_base_url,
                "ollamaVersion": "test", "details": {"family": "fake", "parameterSize": "0B", "quantization": "none"},
                "capabilities": ["completion", "tools"], "message": "fake"}

    monkeypatch.setattr(runner_mod, "probe_ollama", fake_probe)
    return fake_probe


def set_condition(services: Services, condition: str = "adaptive", **extra: Any) -> None:
    conn = services.store.connect()
    try:
        services.store.update_session(conn, condition=condition, **extra)
    finally:
        conn.close()


def value_of(services: Services, game: str, setting_id: str) -> Any:
    conn = services.store.connect()
    try:
        return services.store.values(conn, game)[setting_id]
    finally:
        conn.close()
