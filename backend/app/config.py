"""Runtime configuration.

All paths are derived from the project folder (never from a machine-specific location), so the same
code runs on Windows and macOS. Values can be overridden with environment variables or a `.env` file
in the project root (see `.env.example`).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from math import isfinite
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dependency is in requirements.txt
        return
    load_dotenv(env_file, override=False)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _ollama_timeout() -> float:
    # Preserve existing .env files that used the original seconds-suffixed name.
    name = "OLLAMA_TIMEOUT" if os.environ.get("OLLAMA_TIMEOUT", "").strip() else "OLLAMA_TIMEOUT_S"
    value = _float(name, 90.0)
    return value if isfinite(value) and value > 0 else 90.0


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _path(name: str, default: Path) -> Path:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    p = Path(raw).expanduser()
    return p if p.is_absolute() else (PROJECT_ROOT / p)


@dataclass(frozen=True)
class Settings:
    project_root: Path
    catalog_dir: Path
    scenario_dir: Path
    db_path: Path
    backup_dir: Path
    ollama_base_url: str
    ollama_model: str
    ollama_timeout_s: float
    ollama_think: bool
    ollama_temperature: float
    ollama_num_ctx: int
    agent_max_tool_rounds: int
    agent_deadline_s: float
    backend_host: str
    backend_port: int
    frontend_port: int
    store_chat_history: bool
    cors_origins: list[str] = field(default_factory=list)
    agent_fast_path: bool = True

    @property
    def backend_connect_host(self) -> str:
        return {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(self.backend_host, self.backend_host)

    @property
    def backend_url(self) -> str:
        host = self.backend_connect_host
        return f"http://[{host}]:{self.backend_port}" if ":" in host else f"http://{host}:{self.backend_port}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv()
    data_dir = PROJECT_ROOT / "data"
    db_path = _path("CSC2524_DB_PATH", data_dir / "local" / "app.db")
    frontend_port = _int("FRONTEND_PORT", 5173)
    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    if not origins:
        origins = [f"http://127.0.0.1:{frontend_port}", f"http://localhost:{frontend_port}"]
    return Settings(
        project_root=PROJECT_ROOT,
        catalog_dir=data_dir / "catalogs",
        scenario_dir=data_dir / "scenarios",
        db_path=db_path,
        backup_dir=db_path.parent / "backups",
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/"),
        # Deliberately no silent default model: the exact tag must come from `ollama list` via .env.
        ollama_model=os.environ.get("OLLAMA_MODEL", "").strip(),
        ollama_timeout_s=_ollama_timeout(),
        ollama_think=_bool("OLLAMA_THINK", False),
        ollama_temperature=_float("OLLAMA_TEMPERATURE", 0.2),
        ollama_num_ctx=_int("OLLAMA_NUM_CTX", 8192),
        agent_max_tool_rounds=_int("AGENT_MAX_TOOL_ROUNDS", 2),
        agent_deadline_s=_float("AGENT_DEADLINE_S", 150.0),
        backend_host=os.environ.get("BACKEND_HOST", "127.0.0.1").strip(),
        backend_port=_int("BACKEND_PORT", 8765),
        frontend_port=frontend_port,
        store_chat_history=_bool("STORE_CHAT_HISTORY", True),
        cors_origins=origins,
        agent_fast_path=_bool("AGENT_FAST_PATH", True),
    )
