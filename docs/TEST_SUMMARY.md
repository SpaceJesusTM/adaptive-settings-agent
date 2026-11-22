# Test summary (latest verified runs: 2026-11-22 macOS arm64 & 2026-11-21 Windows PC)

## 1. macOS arm64 comprehensive pass verification (2026-11-22)

Environment: macOS `Darwin 27.0.0` (`arm64` Apple Silicon), Python `3.11.6` (`.venv`), Node.js `v22.20.0`, Ollama `0.40.15`, model `gemma4:12b-it-q4_K_M` (`11.9B`, `Q4_K_M`, `OLLAMA_TIMEOUT=180`, `AGENT_DEADLINE_S=360`), Google Chrome (`PW_CHANNEL=chrome`). Generated screenshots, backups, and live model transcripts stay local in git-ignored folders.

| Suite | Command | Result |
|---|---|---|
| Backend unit/integration & portability | `.venv/bin/pytest -c backend/pytest.ini` | **97 passed** (incl. `test_comprehensive_setup.py`, `test_crosshair_and_hud.py`, `test_portability.py`) |
| Production build & TypeScript | `npm --prefix frontend run build` | pass (`340.96 kB` JS / `102.22 kB` gzip, `52.61 kB` CSS / `10.34 kB` gzip) |
| Frontend unit | `npm --prefix frontend test` | **15 passed** (`menu.test.tsx` 10, `workspace.test.tsx` 5) |
| End-to-end journeys | `PW_CHANNEL=chrome npm --prefix frontend run e2e` | **17/17 passed** (`28.4 s`) |
| Screenshot generation | `PW_CHANNEL=chrome npm --prefix frontend run screenshots` | **2/2 passed** (`11.9 s`, 8 PNGs in git-ignored `docs/screenshots/`) |
| Live environment smoke check | `.venv/bin/python scripts/smoke_check.py --real-model` | **8/8 checks OK** (real structured-output probe `10.3 s`, `eval_count=10`) |
| Curated real-model evaluation | `.venv/bin/python scripts/run_model_eval.py --cases perf_goal explain_aa focused_vsync cs2_full_setup well_configured model_failure` | Run `20261122-143214` (`1628.9 s`, **9 turns**): **7 AI turns** (`133,560 ms` min, `150,275 ms` median, `283,820 ms` max), **2 labelled fallback turns**, `3` `no_op` items filtered by validator, `valuesUnchanged: True` across all 6 cases |
| Live browser preview (`preview_*`) | T3 preview at `1440×900` & `1280×720` (Participant, Experimenter, Crosshair, HUD Edge, `New`, `?view=workspace`) | Zero console errors, zero failed network requests; caught & fixed `StudyBar` Experimenter shrink, top-right `.toasts`, select caret alignment, and sticky Workspace Apply bar |

### Live local `gemma4:12b-it-q4_K_M` case observations (`20261122-143214/summary.md`)
* `perf_goal` (4 turns): all 4 answered by `gemma4:12b-it-q4_K_M` — Turn 1 (`283.8 s`) staged **12** recommendations across Video & General (`0` filtered); Turns 2–4 (`140.9 s`, `182.8 s`, `150.3 s`) answered explanations / preference suggestion with `0` staged (`valuesUnchanged = True`).
* `explain_aa` (1 turn): answered by `gemma4:12b-it-q4_K_M` (`133.6 s`, `intent=explain`, `staged=0`).
* `focused_vsync` (1 turn): answered by `gemma4:12b-it-q4_K_M` (`147.7 s`, returned `intent=explain` with 1 advisory recommendation `VSync: On -> Off`, `staged=0`).
* `cs2_full_setup` (1 turn, `fresh_install_comprehensive`): exceeded `AGENT_DEADLINE_S=360` at `360,112 ms` during multi-batch Apple Silicon local generation and transitioned cleanly to the **labelled rule-based fallback**, staging **21** categorized items across Video, Audio, and Game (`valuesUnchanged = True`).
* `well_configured` (1 turn, `well_configured_competitive`): answered by `gemma4:12b-it-q4_K_M` (`228.1 s`); validator removed **3** `no_op` items cleanly and staged `1` remaining setting (`Experimental Sharpening: Off -> On`).
* `model_failure` (1 turn): unreachable Ollama (`19 ms`) triggered the labelled fallback immediately with **12** Video items staged (`valuesUnchanged = True`).

## 2. Original Windows research baseline (2026-11-21)

These baseline results describe the initial Windows prototype prior to the comprehensive pass. See the [current CI workflow](../.github/workflows/ci.yml) for CI commands.

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

* `test_comprehensive_setup.py` & `test_crosshair_and_hud.py` — intent scope classification (`explain_only` precedence, `single_setting`, `focused`, `category_optimization`, `full_game_setup`), idempotent auto-staging (`idx_proposals_run_autostage`), zero forced churn in `well_configured_competitive`, multi-batch partial-coverage deadline guard, personal/keybind safety enforcement, VALORANT 15-profile Crosshair CRUD + Riot `0;P;...` code parser + ADS/Sniper gating, and CS2 HUD Edge `Done` immediate apply separate from Video pending drafts.
* **Frontend (`menu.test.tsx`, `workspace.test.tsx`)** — A/B row parity, no AI affordances in baseline, Participant vs. Experimenter drawer gating, direct manual Pinned edits & CS2 Video pending-draft conflict modal, reactive SVG VALORANT crosshair preview, CS2 HUD Edge safezone inset math, dependent disabled rows, segmented/dropdown/slider/keybind/color controls.
* **E2E (`frontend/e2e/journeys.spec.ts`, 17 specs)** — baseline manual edit/reload/history/undo, search, CS2 explicit Apply & presets, Participant chrome hiding, A/B parity across both games, auto-staged single & >12-item comprehensive setups, Pinned manual edits/locks/undo, locked-item blocking, preference confirmation with scope, detached `/?view=workspace` cross-window sync, `Discover` (`Prepare for review`) cross-game transfer & reload hold + simulated context event, VALORANT Crosshair import/reload persistence, and CS2 HUD Edge `Done` independence + `New` tab.

## Not tested
* Linux, additional GPUs/hardware, or other Ollama versions/models (Windows 11 + RTX 4080 SUPER baseline and macOS `Darwin 27.0.0` `arm64` are the verified environments).
* Real VALORANT or CS2 installations: the prototype never touches game files and measures no in-game FPS or latency.
* Human participants: no user study was run; comprehension, usability, and trust claims remain open (see [PARTICIPANT_PILOT.md](PARTICIPANT_PILOT.md)).
