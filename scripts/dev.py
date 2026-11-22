"""Start the prototype locally (Windows and macOS; no shell-specific syntax).

  python scripts/dev.py              # backend (FastAPI) + frontend (Vite dev server, hot reload)
  python scripts/dev.py --serve      # build the frontend once, then serve everything from the backend (one port)
  python scripts/dev.py --backend    # backend only
  python scripts/dev.py --frontend   # frontend only

Press Ctrl+C to stop. Uses the project-local .venv interpreter when it exists.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from _common import BACKEND, FRONTEND, bootstrap_backend_imports, utf8_stdout, venv_python


def port_free(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return False
    except OSError:
        return True


def start(cmd: list[str], cwd: Path) -> subprocess.Popen:
    kwargs: dict = {"cwd": str(cwd)}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description="Run the CSC2524 prototype locally.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--backend", action="store_true", help="backend only")
    group.add_argument("--frontend", action="store_true", help="frontend dev server only")
    group.add_argument("--serve", action="store_true", help="build the frontend, then serve it from the backend")
    parser.add_argument("--reload", action="store_true", help="auto-reload the backend on code changes")
    args = parser.parse_args()
    bootstrap_backend_imports()
    from app.config import get_settings

    settings = get_settings()
    py = str(venv_python()) if venv_python().exists() else sys.executable
    npm = shutil.which("npm")
    host, bport, fport = settings.backend_host, settings.backend_port, settings.frontend_port
    procs: list[subprocess.Popen] = []

    want_backend = not args.frontend
    want_frontend = not args.backend and not args.serve
    if want_backend and not port_free(settings.backend_connect_host, bport):
        print(f"Port {bport} is already in use. Stop the other process or set BACKEND_PORT in .env.")
        return 1
    if want_frontend and not port_free("127.0.0.1", fport):
        print(f"Port {fport} is already in use. Stop the other process or set FRONTEND_PORT in .env.")
        return 1
    if (want_frontend or args.serve) and not npm:
        print("npm was not found on PATH. Install Node.js 24 LTS or 22.12+ in the 22.x line.")
        return 1
    if (want_frontend or args.serve) and not (FRONTEND / "node_modules").is_dir():
        print("Installing frontend dependencies from the lockfile (npm ci)...")
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=str(FRONTEND), check=True)
    if args.serve:
        print("Building the frontend (npm run build)...")
        subprocess.run([npm, "run", "build"], cwd=str(FRONTEND), check=True)

    try:
        if want_backend:
            cmd = [py, "-m", "uvicorn", "app.main:app", "--app-dir", str(BACKEND), "--host", host, "--port", str(bport)]
            if args.reload:
                cmd += ["--reload", "--reload-dir", str(BACKEND / "app")]
            procs.append(start(cmd, BACKEND.parent))
            print(f"Backend:  {settings.backend_url}/api/health  (model: {settings.ollama_model or 'not set -> fallback'})")
        if want_frontend:
            procs.append(start([npm, "run", "dev"], FRONTEND))
            print(f"Frontend: http://127.0.0.1:{fport}/")
        if args.serve:
            print(f"Open:     {settings.backend_url}/  (built frontend served by the backend)")
        print("Press Ctrl+C to stop.")
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
        failed = [p for p in procs if p.poll() not in (None, 0)]
        if failed:
            print("A process exited unexpectedly; stopping the others.")
            return 1
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        for p in procs:
            stop(p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
