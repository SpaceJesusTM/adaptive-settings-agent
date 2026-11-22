"""Reset the local demo database to a scenario's experimental initial state (non-destructive: backs up first).

Examples
  python scripts/reset_demo.py                          # full reset to the 'default' scenario
  python scripts/reset_demo.py --scenario valorant_history_new_cs2
  python scripts/reset_demo.py --mode ai_only           # keep setting values/history, clear AI session state
  python scripts/reset_demo.py --list

Prefer the in-app "Reset" control while the backend is running; this script edits the same SQLite file.
"""
from __future__ import annotations

import argparse
import sys

from _common import bootstrap_backend_imports, ensure_supported_python, utf8_stdout


def main() -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description="Reset the CSC2524 prototype's local demo state.")
    parser.add_argument("--scenario", default="default", help="scenario name from data/scenarios (default: default)")
    parser.add_argument("--mode", choices=["full", "ai_only"], default="full",
                        help="full = experimental initial state; ai_only = keep values/history, clear AI session state")
    parser.add_argument("--no-backup", action="store_true", help="skip the JSON backup (not recommended)")
    parser.add_argument("--list", action="store_true", help="list available scenarios and exit")
    args = parser.parse_args()
    ensure_supported_python()
    bootstrap_backend_imports()

    from app.catalog.loader import load_registry
    from app.config import get_settings
    from app.domain.scenarios import list_scenarios, reset
    from app.domain.store import Store

    settings = get_settings()
    if args.list:
        for sc in list_scenarios(settings.scenario_dir):
            print(f"{sc['name']:28s} {sc['title']}")
        return 0
    store = Store(settings.db_path, load_registry(settings.catalog_dir))
    result = reset(store, settings.scenario_dir, settings.backup_dir, args.scenario, args.mode, backup=not args.no_backup)
    print(f"Reset to scenario '{result['scenario']}' (mode: {result['mode']}).")
    print(f"Database: {settings.db_path}")
    if result["backup"]:
        print(f"Backup of the previous state: {result['backup']}")
    print(f"Condition: {result['session']['condition']} | selected game: {result['session']['selectedGame']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
