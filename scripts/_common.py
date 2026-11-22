"""Shared helpers for the cross-platform helper scripts (no shell-specific syntax anywhere)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def bootstrap_backend_imports() -> None:
    """Make `import app` work when a script is run from any working directory."""
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))


def utf8_stdout() -> None:
    """Windows consoles default to a legacy code page; force UTF-8 so labels like '–' print correctly."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def venv_python() -> Path:
    """Project-local virtual environment interpreter (Windows: .venv\\Scripts\\python.exe, macOS: .venv/bin/python)."""
    win = ROOT / ".venv" / "Scripts" / "python.exe"
    posix = ROOT / ".venv" / "bin" / "python"
    return win if os.name == "nt" else posix


def ensure_supported_python() -> None:
    if sys.version_info < (3, 11):
        sys.exit(f"Python 3.11+ is required (found {sys.version.split()[0]}).")
