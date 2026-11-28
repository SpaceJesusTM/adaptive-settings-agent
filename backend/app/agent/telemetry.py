"""Per-turn inference measurements that survive timeout and cancellation."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnTelemetry:
    calls: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    phases: dict[str, int] = field(default_factory=dict)

    def phase(self, name: str, started: float) -> None:
        self.phases[name] = self.phases.get(name, 0) + round((time.perf_counter() - started) * 1000)

    async def invoke(self, step: str, model, messages, *, timeout: float | None = None):
        record = {"step": step, "status": "started"}
        self.calls.append(record)
        started = time.perf_counter()
        try:
            if timeout is None:
                out = await model.ainvoke(messages)
            else:
                async with asyncio.timeout(timeout):
                    out = await model.ainvoke(messages)
            raw = out.get("raw") if isinstance(out, dict) else out
            meta = getattr(raw, "response_metadata", {}) or {}
            usage = getattr(raw, "usage_metadata", {}) or {}
            record["status"] = "completed"
            if isinstance(out, dict):
                record["parsed"] = out.get("parsed") is not None
                error = out.get("parsing_error")
                if error:
                    record["parseError"] = type(error).__name__
            record["inputTokens"] = usage.get("input_tokens", meta.get("prompt_eval_count"))
            record["outputTokens"] = usage.get("output_tokens", meta.get("eval_count"))
            for dst, src in (
                ("promptEvalMs", "prompt_eval_duration"), ("evalMs", "eval_duration"),
                ("loadMs", "load_duration"), ("providerTotalMs", "total_duration"),
            ):
                duration = meta.get(src)
                if isinstance(duration, (int, float)):
                    record[dst] = round(duration / 1e6, 3)
            return out
        except asyncio.TimeoutError:
            record["status"] = "timeout"
            raise
        except asyncio.CancelledError:
            record["status"] = "cancelled"
            raise
        except Exception as exc:
            record["status"] = "error"
            record["errorType"] = type(exc).__name__
            raise
        finally:
            record["ms"] = round((time.perf_counter() - started) * 1000)
