# Progress log (resume point for a fresh session)

## Current status (2026-11-21)
**All phases 0-7 implemented and verified on Windows.** macOS remains documented but untested.

**Next actionable steps (optional, P1/P2):**
1. Run the macOS instructions on a Mac and record results in `TEST_SUMMARY.md` (and fix anything platform-specific).
2. If a newer VALORANT source documents the post-12.07 section layout or the crosshair editor, update
   `data/catalogs/valorant.json` (drop the `inferred` flags / add the Crosshair tab) and re-run tests + `catalog_report.py`.
3. Run a pilot user study (see `PAPER_IMPLEMENTATION_NOTES.md`, “Proposed first human evaluation”).

## Environment (observed 2026-11-21, Windows host)
| Item | Observed |
|---|---|
| OS | Windows 11 Pro 10.0.26300 |
| Python | 3.11.9 (`python`), project venv `.venv` |
| Node / npm | v24.15.0 / 11.12.1 |
| Ollama | 0.40.17 at `http://127.0.0.1:11434` |
| Model | `gemma4:12b-it-q4_K_M` (user-approved pull; gemma4, 11.9B, Q4_K_M, ID 6114515d63c1) |
| GPU / CPU / RAM | RTX 4080 SUPER 16 GB / Core Ultra 7 265F / 64 GB |
| Git | none — no Git or GitHub actions were taken (deferred to the user) |

## Completed work
* Research + catalogues: VALORANT 74 settings (22 official-doc, 32 official-screenshot, 6 partial, 14 secondary-only),
  CS2 121 settings (game files, build 2000948). Audit: `GAME_SETTINGS_AUDIT.md`; full table: `CATALOG_REPORT.md`.
* Backend: catalogue loader/validator, SQLite store (single write path, revisions, history/undo, presets, pins/locks),
  proposal engine (all-or-nothing, idempotent, conflict reasons), profile (session goals vs durable preferences,
  evidence, simulated context), deterministic recommender with hold rule, LangGraph agent (read-only tools, native
  tool calls, JSON-schema output, validator, one repair, deadline, cancel), labelled offline fallback, run traces, API.
* Frontend: VALORANT and CS2 menu shells over one engine, shared accessible controls, search, history/undo, CS2 native
  explicit apply and presets, crosshair preview; adaptive layer (Relevant now, chat with provenance, layered
  explanations, highlight of original rows, review tray with edit/apply/reject, pins, locks, preferences, trace view).
* Scripts: `dev.py`, `reset_demo.py`, `smoke_check.py`, `run_model_eval.py`, `replay_scenarios.py`, `catalog_report.py`.
* Docs: README (Windows + macOS), plan, decisions (D-01…D-16), audit, model setup, API, demo script, acceptance scripts,
  test summary, paper notes, evidence (model runs, scenario replays, screenshots).

## Test results (actual) — details in `TEST_SUMMARY.md`
* Backend pytest **62 passed**; frontend Vitest **10 passed**; typecheck + build pass; Playwright **12/12** in 5
  consecutive runs; smoke check **9/9**; real-model evaluation final run `docs/evidence/model_runs/20261121-105132/`
  (12/12 correct intents, 3.1–8.0 s, no values changed by the assistant).

## Known limitations / open issues
* VALORANT: 19 section placements after Patch 12.07 are inferred; crosshair tab not simulated; 14 settings secondary-only.
* Model variability exists between runs (bounded by validation + one repair); thinking mode is slower and less reliable.
* E2E runs against the production build; an intermittent exit of a second Vite dev server on Windows was observed and
  avoided, not root-caused.
* The only change outside this folder: the user-approved `ollama pull gemma4:12b-it-q4_K_M` (Ollama's model store),
  plus normal pip/npm download caches.
