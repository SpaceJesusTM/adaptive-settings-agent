"""Environment and integration smoke check (Windows and macOS).

  python scripts/smoke_check.py                 # toolchain, catalogues, DB, Ollama + exact model tag
  python scripts/smoke_check.py --backend       # also check a running backend (BACKEND_PORT)
  python scripts/smoke_check.py --real-model    # also run ONE tiny real structured-output request

Exit code 0 when all required checks pass. Optional checks are reported but do not fail the run.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from _common import ROOT, bootstrap_backend_imports, utf8_stdout

RESULTS: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    RESULTS.append((status, name, detail))
    print(f"[{status:4s}] {name}" + (f" - {detail}" if detail else ""))


def http_json(url: str, payload: dict | None = None, timeout: float = 5.0) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description="Smoke-check the CSC2524 prototype environment.")
    parser.add_argument("--backend", action="store_true", help="also query a running backend")
    parser.add_argument("--real-model", action="store_true", help="run one tiny real request against the configured model")
    args = parser.parse_args()
    bootstrap_backend_imports()

    print(f"Host: {platform.system()} {platform.release()} ({platform.machine()}), Python {sys.version.split()[0]}")
    record("OK" if sys.version_info[:2] == (3, 11) else "WARN", "Python (tested line: 3.11)", sys.version.split()[0])

    node = shutil.which("node")
    npm = shutil.which("npm")
    if node:
        ver = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
        major, minor = map(int, ver.lstrip("v").split(".")[:2]) if ver.startswith("v") else (0, 0)
        supported = major == 24 or (major == 22 and minor >= 12)
        record("OK" if supported else "WARN", "Node.js (22.12+ in 22.x or 24.x)", ver)
    else:
        record("WARN", "Node.js", "not found (needed only for the frontend dev server/build)")
    record("OK" if npm else "WARN", "npm", npm or "not found")

    try:
        from app.catalog.loader import load_registry
        from app.config import get_settings
        settings = get_settings()
        reg = load_registry(settings.catalog_dir)
        counts = {g: len(reg.settings(g)) for g in reg.games}
        record("OK", "Catalogues load and validate", json.dumps(counts))
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "Catalogues load and validate", repr(exc))
        return summary()

    try:
        from app.domain.scenarios import ensure_seeded
        from app.domain.store import Store
        with tempfile.TemporaryDirectory(prefix="csc2524 smoke ") as tmp:
            store = Store(Path(tmp) / "smoke test.db", reg)
            ensure_seeded(store, settings.scenario_dir, Path(tmp) / "backups")
            conn = store.connect()
            n = conn.execute("SELECT COUNT(*) AS n FROM setting_values").fetchone()["n"]
            conn.close()
        record("OK", "SQLite create + seed (path with spaces)", f"{n} values")
    except Exception as exc:  # noqa: BLE001
        record("FAIL", "SQLite create + seed", repr(exc))

    base = settings.ollama_base_url
    model = settings.ollama_model
    try:
        ver = http_json(f"{base}/api/version")
        record("OK", "Ollama reachable", f"{base} (version {ver.get('version')})")
        tags = http_json(f"{base}/api/tags")
        names = {m.get("name") for m in tags.get("models", [])}
        if not model:
            record("WARN", "OLLAMA_MODEL configured", "empty: the app will use the labelled offline fallback")
        elif model in names:
            show = http_json(f"{base}/api/show", {"model": model})
            det = show.get("details", {})
            record("OK", "Configured model installed", f"{model} | {det.get('family')} {det.get('parameter_size')} "
                                                       f"{det.get('quantization_level')} | caps: {', '.join(show.get('capabilities', []))}")
        else:
            record("WARN", "Configured model installed", f"'{model}' not in `ollama list` (no substitution is made)")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        record("WARN", "Ollama reachable", f"{base}: {exc} (the app will run in fallback mode)")

    if args.real_model and not model:
        record("FAIL", "Real structured-output request", "Set OLLAMA_MODEL to an installed tag.")
    elif args.real_model:
        try:
            t0 = time.perf_counter()
            out = http_json(f"{base}/api/chat", {
                "model": model, "stream": False, "think": False, "options": {"temperature": 0},
                "format": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
                "messages": [{"role": "user", "content": "Return JSON with ok=true."}]},
                timeout=settings.ollama_timeout_s)
            content = json.loads(out["message"]["content"])
            record("OK" if content.get("ok") is True else "FAIL", "Real structured-output request",
                   f"{(time.perf_counter() - t0):.1f}s, eval_count={out.get('eval_count')}")
        except Exception as exc:  # noqa: BLE001
            record("FAIL", "Real structured-output request", repr(exc))

    if args.backend:
        try:
            port = settings.backend_port
            health = http_json(f"{settings.backend_url}/api/health")
            status = http_json(f"{settings.backend_url}/api/model/status")
            record("OK", "Backend health", f"port {port}, version {health.get('version')}, AI: {status.get('indicatorLabel')}")
        except Exception as exc:  # noqa: BLE001
            record("FAIL", "Backend health", repr(exc))
    return summary()


def summary() -> int:
    failed = [r for r in RESULTS if r[0] == "FAIL"]
    print(f"\n{len(RESULTS)} checks: {len(failed)} failed, {sum(1 for r in RESULTS if r[0] == 'WARN')} warnings.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
