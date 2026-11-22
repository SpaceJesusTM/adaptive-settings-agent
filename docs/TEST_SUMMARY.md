# Test summary (actual results, Windows test PC, 2026-11-21)

These results describe the original research prototype. The corresponding screenshots, generated replays and model transcripts stay local. See the [current CI workflow](../.github/workflows/ci.yml) for the public repository’s test commands.

Environment: Windows 11 Pro 10.0.26300 (Python's `platform` reports it as "Windows 10"), Python 3.11.9 (project
`.venv`), Node 24.15.0, Ollama 0.40.17, model `gemma4:12b-it-q4_K_M`, Microsoft Edge (Playwright channel `msedge`).

| Suite | Command | Result |
|---|---|---|
| Backend unit/integration | `cd backend; python -m pytest` | **62 passed** (2.7 s) |
| Frontend unit | `cd frontend; npm test` | **10 passed** |
| Type checks | `cd frontend; npm run typecheck` | pass (app + node tooling configs) |
| Production build | `cd frontend; npm run build` | pass (JS 298.6 kB / 91.9 kB gzip, CSS 43.2 kB) |
| End-to-end journeys | `cd frontend; npm run e2e` | **12/12 passed in each of 5 consecutive runs** (~9 s per run) against the production build |
| Screenshot generation | `REAL_AI=1 npm run screenshots` | 3/3 passed; figures in `docs/screenshots/` (adaptive answers from the real model) |
| Environment smoke check | `python scripts/smoke_check.py --backend --real-model` | **9/9 checks OK** (incl. one real structured request, 8.9 s) |
| Real-model evaluation | `python scripts/run_model_eval.py` | final run `docs/evidence/model_runs/20261121-105132/`: 12/12 model turns correct intent, 3.1/5.0/8.0 s; see `model_runs/README.md` for all iterations |
| Deterministic replays | `python scripts/replay_scenarios.py` | 6/6 scenarios produced; `docs/evidence/scenario_replays/` |
| Single-port serve mode | `python scripts/dev.py --serve` (port 8767 for the check) | index, assets, SPA deep link and API returned 200; a `../` traversal request returned `index.html`, not a file |

## What the automated tests cover

**Backend (`backend/tests/`)**
* `test_catalog.py` — ≥30 well-verified interactive settings per game; exact current tab lists; unique game-prefixed IDs
  and canonical paths; no ID overlap between games; provenance fields on every setting; option/range/sample/default/hint
  domains; Riot-documented labels and paths; CS2 labels from game files and the Sept-2026 crosshair default; no
  *Raw Input*-type settings; CS2 preset = video preset files; honest verification mix; loader rejects duplicate IDs,
  out-of-domain samples, unknown sources, broken dependencies, proposable keybinds.
* `test_store.py` — label/value normalisation, strict vs snapped numbers, key-name validation, availability rules;
  manual change + history + undo + double-undo refusal; undo refused after a later change; stale revision → 409;
  idempotent requests; invalid values and dependencies write nothing (bundle atomicity); game separation; presets;
  persistence across restart; condition switch changes no values; 6 concurrent writers serialised.
* `test_proposals.py` — **staging never changes values**; apply only selected items with `ai_applied` history; bundle
  with an item locked after staging applies nothing; stale baseline conflict then user rebase; idempotent apply and
  refused double apply; 4 simultaneous apply requests → exactly one applies; reject changes nothing and records
  evidence; edited values; unsafe items (sensitivity, keybind, wrong game, invalid option, locked) rejected/blocked;
  adaptive-only API.
* `test_agent.py` — validator removes invented IDs, other-game IDs **and labels**, locked, invalid, no-op,
  non-proposable, unavailable and over-limit items, strips numeric performance claims and URLs, flags claimed actions;
  full LangGraph run with a scripted model including a model-requested tool call; prompt-injection attempt changes
  nothing; a request for changes without recommendations triggers exactly one repair; already-saved preferences are not
  re-suggested; malformed output → labelled fallback; timeout → fallback; single-flight + cancel; baseline has no chat;
  fallback explain/navigate/preference; cross-game ranking uses abstract preferences only (no sensitivity, CS2 values
  untouched); Relevant now hold rule and dismissal.
* `test_api.py` — health/catalog/state/search; manual change, stale revision, invalid value, history, undo over HTTP;
  CS2 explicit batch apply; adaptive gating; full chat → stage → apply → undo flow; context event + preference
  correction (only explicit sources accepted); reset backup, export/import round trip, `ai_only` reset, scenario path
  traversal rejected.
* `test_portability.py` — project-relative paths; no machine-specific paths in source; SQLite in a folder with spaces;
  Unicode round trip; UTF-8 catalogues without BOM; helper scripts run as subprocesses.

**Frontend unit (`frontend/src/test/menu.test.tsx`)** — identical rows and order in both conditions; no AI
affordances in the baseline even with pending proposals; staged/lock affordances on the original rows in the adaptive
condition; highlight never reorders rows; dependent rows disabled; segmented keyboard/click; dropdown offers only
catalogue options; slider clamping; keybind capture maps to game key names; CS2 explicit-apply edits stay local.

**E2E (`frontend/e2e/journeys.spec.ts`)** — A: manual change, reload persistence, history, undo; search to canonical
row; CS2 pending video edits and Apply Changes; CS2 preset. Parity in both games. B/D: fallback suggestions do nothing
until staged and applied, then undo; locks; preference saved only after confirmation with chosen scope. C/E: cross-game
CS2 suggestions citing VALORANT, values unchanged; Relevant now holds on reload and does not reinsert a dismissed
card; simulated context event labelled.

## Issues found and fixed during testing (selection)
* Zustand v5 selectors returning a fresh `[]` caused an infinite render loop in the adaptive panel → stable `EMPTY`.
* Real model over-asked clarifying questions → intent decision procedure (evidence: `model_runs/20261121-101359`).
* Real model misclassified a cross-game request once → deterministic repair rule + test.
* E2E: a race in one test (captured cards before render) fixed; intermittent loss of a second Vite dev server
  (5174) when running next to the dev server on Windows — E2E now builds the frontend and lets the isolated backend serve
  it, after which 5/5 consecutive runs passed. The root cause of the Vite exits was not determined.

## Not tested
* **macOS** (no Mac available) — instructions are documented but unverified.
* Linux, other GPUs/hardware, other Ollama versions or models.
* The real games: the prototype never touches them, so no in-game effect is measured or claimed.
* Human participants: no user study was run; nothing here establishes comprehension, usability or trust benefits.
