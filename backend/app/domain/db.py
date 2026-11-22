"""SQLite persistence: deterministic, versioned schema bootstrap and connection helpers.

Concurrency model: each request opens its own connection; writers use `BEGIN IMMEDIATE` so concurrent
mutations are serialised by SQLite's write lock (no half-applied bundles), WAL lets readers proceed.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 2

MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

    CREATE TABLE IF NOT EXISTS setting_values (
        game TEXT NOT NULL,
        setting_id TEXT NOT NULL,
        value_json TEXT NOT NULL,
        revision INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (game, setting_id)
    );

    CREATE TABLE IF NOT EXISTS game_state (
        game TEXT PRIMARY KEY,
        revision INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS change_batches (
        id TEXT PRIMARY KEY,
        game TEXT NOT NULL,
        source TEXT NOT NULL,
        label TEXT,
        proposal_id TEXT,
        condition TEXT,
        session_id TEXT,
        client_request_id TEXT UNIQUE,
        undoes_batch_id TEXT,
        undone_by_batch_id TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS change_events (
        id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL REFERENCES change_batches(id),
        game TEXT NOT NULL,
        setting_id TEXT NOT NULL,
        old_value_json TEXT NOT NULL,
        new_value_json TEXT NOT NULL,
        revision_after INTEGER NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_events_game ON change_events(game, created_at);
    CREATE INDEX IF NOT EXISTS idx_events_batch ON change_events(batch_id);

    CREATE TABLE IF NOT EXISTS pins (
        game TEXT NOT NULL, setting_id TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (game, setting_id)
    );
    CREATE TABLE IF NOT EXISTS locks (
        game TEXT NOT NULL, setting_id TEXT NOT NULL, created_at TEXT NOT NULL,
        PRIMARY KEY (game, setting_id)
    );

    CREATE TABLE IF NOT EXISTS proposals (
        id TEXT PRIMARY KEY,
        game TEXT NOT NULL,
        source TEXT NOT NULL,
        run_id TEXT,
        title TEXT,
        status TEXT NOT NULL,
        condition TEXT,
        session_id TEXT,
        applied_batch_id TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS proposal_items (
        id TEXT PRIMARY KEY,
        proposal_id TEXT NOT NULL REFERENCES proposals(id),
        position INTEGER NOT NULL,
        setting_id TEXT NOT NULL,
        baseline_value_json TEXT NOT NULL,
        baseline_revision INTEGER NOT NULL,
        proposed_value_json TEXT NOT NULL,
        edited_value_json TEXT,
        status TEXT NOT NULL,
        status_reason TEXT,
        why TEXT,
        tradeoff TEXT,
        confidence TEXT,
        dimensions_json TEXT NOT NULL DEFAULT '[]',
        based_on TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_items_proposal ON proposal_items(proposal_id);

    CREATE TABLE IF NOT EXISTS preferences (
        id TEXT PRIMARY KEY,
        dimension TEXT NOT NULL,
        direction TEXT NOT NULL,
        scope TEXT NOT NULL,
        session_id TEXT,
        game TEXT,
        origin_game TEXT,
        source TEXT NOT NULL,
        note TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS evidence (
        id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        dimension TEXT,
        game TEXT,
        setting_id TEXT,
        proposal_id TEXT,
        detail TEXT,
        session_id TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS session_goals (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        game TEXT NOT NULL,
        text TEXT NOT NULL,
        dimensions_json TEXT NOT NULL,
        source TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS dismissals (
        id TEXT PRIMARY KEY,
        game TEXT NOT NULL,
        setting_id TEXT NOT NULL,
        reason TEXT,
        signature TEXT NOT NULL,
        session_id TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS relevant_now (
        game TEXT PRIMARY KEY,
        items_json TEXT NOT NULL,
        signature TEXT NOT NULL,
        trigger TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS context_events (
        id TEXT PRIMARY KEY,
        game TEXT NOT NULL,
        event_type TEXT NOT NULL,
        session_id TEXT,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        game TEXT NOT NULL,
        session_id TEXT,
        role TEXT NOT NULL,
        content_json TEXT NOT NULL,
        run_id TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS agent_runs (
        id TEXT PRIMARY KEY,
        game TEXT NOT NULL,
        condition TEXT,
        session_id TEXT,
        status TEXT NOT NULL,
        mode TEXT NOT NULL,
        model TEXT,
        goal_excerpt TEXT,
        steps_json TEXT NOT NULL DEFAULT '[]',
        tool_calls_json TEXT NOT NULL DEFAULT '[]',
        validation_json TEXT NOT NULL DEFAULT '{}',
        result_json TEXT,
        proposal_ids_json TEXT NOT NULL DEFAULT '[]',
        error TEXT,
        latency_ms INTEGER,
        started_at TEXT NOT NULL,
        finished_at TEXT
    );

    CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
    """,
    2: """
    ALTER TABLE proposals ADD COLUMN plan_json TEXT;
    ALTER TABLE proposals ADD COLUMN auto_staged INTEGER NOT NULL DEFAULT 0;
    CREATE UNIQUE INDEX IF NOT EXISTS idx_proposals_run_autostage
        ON proposals(run_id) WHERE run_id IS NOT NULL AND auto_staged = 1;

    CREATE TABLE IF NOT EXISTS valorant_crosshair_profiles (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        settings_json TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(text: str | None, default: Any = None) -> Any:
    if text is None:
        return default
    return json.loads(text)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 15000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


@contextmanager
def write_tx(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Serialised write transaction: either everything commits or nothing does."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def bootstrap(conn: sqlite3.Connection) -> int:
    """Apply pending migrations deterministically; returns the resulting schema version."""
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    current = int(row["value"]) if row else 0
    for version in sorted(MIGRATIONS):
        if version <= current:
            continue
        with write_tx(conn):
            # Statements contain no embedded semicolons, so a plain split is safe and keeps the whole
            # migration inside one explicit transaction (executescript would auto-commit).
            for stmt in [s.strip() for s in MIGRATIONS[version].split(";") if s.strip()]:
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(version),),
            )
        current = version
    return current
