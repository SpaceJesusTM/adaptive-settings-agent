"""Truthful local-model status. Ollama is only ever contacted from the server (never from the browser)."""
from __future__ import annotations

import time
from typing import Any, Optional

import httpx

from ..config import Settings

_CACHE: dict[str, Any] = {"at": 0.0, "value": None, "key": None}
CACHE_SECONDS = 8.0


def _response_object(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Expected an Ollama JSON object.")
    return data


async def probe_ollama(settings: Settings, *, force: bool = False) -> dict[str, Any]:
    """Return {'state': connected|unavailable|not_configured, ...} for the exact configured tag."""
    now = time.monotonic()
    key = (settings.ollama_base_url, settings.ollama_model)
    if not force and _CACHE["value"] is not None and _CACHE["key"] == key and now - _CACHE["at"] < CACHE_SECONDS:
        return _CACHE["value"]
    result: dict[str, Any] = {"model": settings.ollama_model or None, "baseUrl": settings.ollama_base_url,
                              "ollamaVersion": None, "details": None, "capabilities": []}
    if not settings.ollama_model:
        result.update(state="not_configured",
                      message="OLLAMA_MODEL is not set. Put the exact tag from `ollama list` in .env.")
    else:
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                ver = _response_object(await client.get(f"{settings.ollama_base_url}/api/version"))
                tags = _response_object(await client.get(f"{settings.ollama_base_url}/api/tags"))
                models = tags.get("models")
                if not isinstance(ver.get("version"), str) or not isinstance(models, list) or any(
                    not isinstance(model, dict) for model in models
                ):
                    raise ValueError("Invalid Ollama version or model list.")
                result["ollamaVersion"] = ver["version"]
                names = [name for model in models for name in (model.get("name"), model.get("model"))]
                if settings.ollama_model not in names:
                    result.update(state="unavailable",
                                  message=f"Model '{settings.ollama_model}' is missing from this Ollama. "
                                          "Check the exact tag with `ollama list`.")
                else:
                    show = await client.post(f"{settings.ollama_base_url}/api/show", json={"model": settings.ollama_model})
                    data = _response_object(show)
                    det = data.get("details", {}) or {}
                    caps = data.get("capabilities", []) or []
                    if not isinstance(det, dict) or not isinstance(caps, list) or any(not isinstance(cap, str) for cap in caps):
                        raise ValueError("Invalid Ollama model metadata.")
                    details = {"family": det.get("family"), "parameterSize": det.get("parameter_size"),
                               "quantization": det.get("quantization_level"), "format": det.get("format")}
                    if any(value is not None and not isinstance(value, str) for value in details.values()):
                        raise ValueError("Invalid Ollama model details.")
                    result["details"] = details
                    result["capabilities"] = caps
                    result.update(state="connected", message="Connected to the local model through Ollama.")
        except httpx.InvalidURL:
            result.update(state="unavailable", message="Check that OLLAMA_BASE_URL is a valid HTTP URL.")
        except httpx.TimeoutException:
            result.update(state="unavailable", message="The Ollama status check timed out. Check the local Ollama service.")
        except httpx.HTTPStatusError as exc:
            result.update(state="unavailable", message=f"Ollama returned HTTP {exc.response.status_code} during the status check. "
                                                        "Check the Ollama service and the configured model.")
        except httpx.RequestError:
            result.update(state="unavailable",
                          message="Cannot reach Ollama. Start the Ollama app or run `ollama serve`, and check OLLAMA_BASE_URL.")
        except ValueError:
            result.update(state="unavailable", message="Ollama returned malformed status data. Check OLLAMA_BASE_URL and Ollama.")
    _CACHE.update(at=now, value=result, key=key)
    return result


def describe_status(probe: dict[str, Any], ai_mode: str) -> dict[str, Any]:
    """Combine the probe with the user's AI mode into the UI's status indicator."""
    if ai_mode == "fallback":
        label, state = "Fallback mode (offline rules, not AI)", "fallback"
    elif probe["state"] == "connected":
        label, state = "Connected local AI", "connected"
    else:
        label, state = "Model unavailable - using offline fallback", "unavailable"
    return {**probe, "indicator": state, "indicatorLabel": label, "aiMode": ai_mode}


def reset_cache() -> None:
    _CACHE.update(at=0.0, value=None, key=None)


def model_label(probe: Optional[dict[str, Any]]) -> Optional[str]:
    if not probe or not probe.get("model"):
        return None
    det = probe.get("details") or {}
    extra = ", ".join(x for x in [det.get("parameterSize"), det.get("quantization")] if x)
    return f"{probe['model']}" + (f" ({extra})" if extra else "")
