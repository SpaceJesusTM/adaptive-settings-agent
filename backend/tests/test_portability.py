"""Cross-platform checks: project-relative paths, spaces in paths, Unicode, subprocess helpers, config loading."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from app import config
from app.config import PROJECT_ROOT, get_settings
from app.domain.store import Change

ROOT = Path(__file__).resolve().parents[2]


def test_config_paths_are_project_relative():
    s = get_settings()
    assert PROJECT_ROOT == ROOT
    assert s.catalog_dir == ROOT / "data" / "catalogs"
    assert s.scenario_dir == ROOT / "data" / "scenarios"
    assert ROOT in s.db_path.parents or os.environ.get("CSC2524_DB_PATH")
    for path_text in json.dumps({"c": str(s.catalog_dir)}).split('"'):
        assert ":\\Users" not in path_text or str(ROOT) in path_text


def test_dotenv_is_loaded_from_project_root(tmp_path, monkeypatch):
    root = tmp_path / "project with spaces"
    root.mkdir()
    (root / ".env").write_text(
        "OLLAMA_MODEL=example-model:q4\nOLLAMA_TIMEOUT=45\nCSC2524_DB_PATH=data/test.db\nFRONTEND_PORT=5179\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "PROJECT_ROOT", root)
    for name in ("OLLAMA_TIMEOUT", "OLLAMA_MODEL", "CSC2524_DB_PATH", "CORS_ORIGINS"):
        # Track absent keys too, since dotenv sets them outside monkeypatch.
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    monkeypatch.setenv("FRONTEND_PORT", "5180")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.ollama_model == "example-model:q4"
        assert settings.ollama_timeout_s == 45
        assert settings.db_path == root / "data" / "test.db"
        assert settings.cors_origins == ["http://127.0.0.1:5180", "http://localhost:5180"]
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(("timeout", "expected"), [(None, 32), ("18.5", 18.5), ("nan", 90), ("0", 90)])
def test_ollama_timeout_and_legacy_alias(tmp_path, monkeypatch, timeout, expected):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("OLLAMA_TIMEOUT_S", "32")
    if timeout is None:
        monkeypatch.delenv("OLLAMA_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("OLLAMA_TIMEOUT", timeout)
    get_settings.cache_clear()
    try:
        assert get_settings().ollama_timeout_s == expected
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(("host", "expected"), [
    ("0.0.0.0", "http://127.0.0.1:8765"),
    ("::", "http://[::1]:8765"),
    ("::1", "http://[::1]:8765"),
    ("localhost", "http://localhost:8765"),
])
def test_backend_url_uses_a_connectable_host(settings, host, expected):
    assert replace(settings, backend_host=host, backend_port=8765).backend_url == expected


def test_no_hardcoded_machine_paths_in_source():
    offenders = []
    for path in list((ROOT / "backend" / "app").rglob("*.py")) + list((ROOT / "scripts").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in ("E:\\VS", "C:\\Users", "/Users/", "VS Code Projects", "LocalAgenticAI"):
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, offenders


def test_database_in_directory_with_spaces_and_unicode_roundtrip(services):
    assert " " in str(services.store.db_path.parent)
    res = services.store.manual_change("cs2", [Change("cs2.audio.eq_profile", "Crisp")], label="EQ – crisp (ünïcødé)")
    assert res["label"] == "EQ – crisp (ünïcødé)"
    hist = services.store.history("cs2")
    assert hist[0]["label"] == "EQ – crisp (ünïcødé)"
    cs2 = services.registry.catalog("cs2")
    assert any("–" in s.description or "…" in s.description or "\"" in s.description for s in cs2.settings)


def test_catalog_files_are_utf8_json():
    for game in ("valorant", "cs2"):
        raw = (ROOT / "data" / "catalogs" / f"{game}.json").read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), "no BOM"
        json.loads(raw.decode("utf-8"))


def test_python_helper_scripts_run_as_subprocess():
    for script in ("reset_demo.py", "smoke_check.py"):
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / script), "--help"], capture_output=True, text=True,
                             encoding="utf-8", timeout=60, cwd=str(ROOT))
        assert out.returncode == 0, out.stderr
        assert "usage" in out.stdout.lower()
