# Test summary (latest verified runs: 2026-11-23 Final HCI Pass on macOS arm64, 2026-11-22 pass & 2026-11-21 Windows baseline)

## 0. Final HCI Design, Adaptivity & Research-Readiness Pass (`2026-11-23`, macOS arm64)

Environment: macOS `Darwin 27.0.0` (`arm64` Apple M4, 24 GB unified memory), Python `3.11.6` (`.venv`), Node.js `v22.20.0`, Ollama `0.40.15`, model `gemma4:12b-it-q4_K_M` (`11.9B`, `Q4_K_M`), Google Chrome (`PW_CHANNEL=chrome`). All checks ran after the final edit on isolated databases without disturbing any running local demo server.

| Suite | Command | Latest Observed Result |
|---|---|---|
| Backend unit/integration & portability | `.venv/bin/pytest -c backend/pytest.ini` | **107 passed** (`3.43 s`, incl. `test_final_pass.py`, `test_comprehensive_setup.py`, `test_crosshair_and_hud.py`, `test_portability.py`) |
| Production build & TypeScript | `npm --prefix frontend run build` | pass (`tsc --noEmit` app + node configs & Vite bundle clean) |
| Frontend unit | `npm --prefix frontend test` | **24 passed** (`992 ms`: `menu.test.tsx` 10, `workspace.test.tsx` 14 incl. History provenance/restage, Already aligned & Needs your decision, `My Priorities` 3 sections/conflicts/facts, Discover `Mark checked`, Cross-Game Comparison cards) |
| End-to-end journeys | `PW_CHANNEL=chrome npm --prefix frontend run e2e` | **22/22 passed** (`23.3 s`, incl. exclusive pop-out auto-restore without reload, History provenance + restage, `well_configured_competitive` aligned review, `My Priorities` facts, `valorant_onboarding_to_cs2` persistence & VSync-Off companion follow-up, cross-game sensitivity/PTT comparison) |
| Live environment smoke check | `CSC2524_DB_PATH=/tmp/csc2524-real-model-verify.db .venv/bin/python scripts/smoke_check.py --real-model` | **8/8 checks OK** (`Real structured-output request - 11.7s, eval_count=10`) |
| Live local `gemma4:12b-it-q4_K_M` 4-turn final check | Inline `Services` run (`aiMode="local"`, isolated DB `/tmp/csc2524-real-model-verify.db`) | **4/4 turns `status=succeeded`, `source=ai`, `filtered=0`, `mut_check=OK` (zero unauthorized mutations):**<br>• Turn 1 (`well_configured_competitive`, VALORANT): **`28.17 s`** (`recs=0`, `aligned=6`, `manual=2`)<br>• Turn 2 (Cross-game comparison in CS2, `valorant_onboarding_to_cs2`): **`35.75 s`** (`intent=explain`, `cg=3`, `aligned=4`, `manual=3`)<br>• Turn 3 (Focused latency in VALORANT `default`): **`24.10 s`** (`recs=2`, `aligned=2`, `manual=2`)<br>• Turn 4 (Comprehensive setup in CS2, `fresh_install_comprehensive`): **`151.02 s`** (`recs=21`, `aligned=5`, `manual=4`) |
| Live isolated Chrome visual inspection | Playwright Chrome screenshot verification against isolated `5183`/`8775` (`1440×900` & `1280×800`) | Captured and visually inspected History drawer, Workspace aligned/manual review, `My Priorities` 3-section + conflict banners, Discover onboarding, Cross-Game chat card, and Exclusive Pop-out main + detached windows; **0 console/page/HTTP errors** |

## 1. Prior macOS arm64 comprehensive pass verification (2026-11-22)

Environment: macOS `Darwin 27.0.0` (`arm64` Apple Silicon M4, 24 GB unified memory), Python `3.11.6` (`.venv`), Node.js `v22.20.0`, Ollama `0.40.15`, model `gemma4:12b-it-q4_K_M` (`11.9B`, `Q4_K_M`, `OLLAMA_TIMEOUT=180`, `AGENT_DEADLINE_S=360`, `OLLAMA_NUM_CTX=8192`, `AGENT_FAST_PATH=true`), Google Chrome (`PW_CHANNEL=chrome`). Generated screenshots, backups, and live model transcripts stay local in git-ignored folders.

| Suite | Command | Result |
|---|---|---|
| Backend unit/integration & portability | `.venv/bin/pytest -c backend/pytest.ini` | **102 passed** (`3.67 s`, incl. `test_comprehensive_setup.py`, `test_crosshair_and_hud.py`, `test_portability.py`, fast-path/search/minor-hint/crosshair-undo regression tests) |
| Production build & TypeScript | `npm --prefix frontend run build` | pass (`tsc --noEmit` app + node configs & Vite bundle clean) |
| Frontend unit | `npm --prefix frontend test` | **17 passed** (`651 ms`: `menu.test.tsx` 10, `workspace.test.tsx` 7 incl. `PreferenceChip` async/retry & `participantStepLabel`) |
| End-to-end journeys | `PW_CHANNEL=chrome npm --prefix frontend run e2e` | **17/17 passed** (`14.1 s`) |
| Screenshot generation | `PW_CHANNEL=chrome npm --prefix frontend run screenshots` | **2/2 passed** (`6.8 s`, 8 PNGs in git-ignored `docs/screenshots/`) |
| Live environment smoke check | `.venv/bin/python scripts/smoke_check.py --real-model` | **8/8 checks OK** (real structured-output probe `2.8 s`, `eval_count=10`) |
| Curated real-model evaluation (post-optimization) | `.venv/bin/python scripts/run_model_eval.py --cases perf_goal explain_aa focused_vsync cs2_full_setup well_configured model_failure` | Run `20261122-164946` (`381.9 s` total vs `1,628.9 s` pre-optimization baseline, **9 turns**): **8/8 AI turns succeeded** (`18,588 ms` min, `31,883 ms` median, `136,038 ms` max), **1 deliberate dead-endpoint fallback** (`9 ms`), `valuesUnchanged: True` across all 6 cases |
| Live browser preview (`preview_*`) | T3 preview at `1280×720` laptop viewport | Verified live Participant mode, Adaptive Workspace, VALORANT Crosshair, and CS2 HUD Edge with zero console/network errors |

### Before vs. after live local `gemma4:12b-it-q4_K_M` case observations (`20261122-143214` → `20261122-164946`)
* `perf_goal` (4 turns): all 4 answered by `gemma4:12b-it-q4_K_M` — Turn 1 **`74.5 s`** (`283.8 s` before; **12** Video changes staged, `0` filtered); Turns 2–4 **`24.1 s / 18.6 s / 29.0 s`** (`140.9 / 182.8 / 150.3 s` before; Turn 4 correctly suggested `session` preference scope, `valuesUnchanged = True`).
* `explain_aa` (1 turn): answered by `gemma4:12b-it-q4_K_M` in **`20.8 s`** (`133.6 s` before; `intent=explain`, `staged=0`, `0` filtered).
* `focused_vsync` (1 turn): answered by `gemma4:12b-it-q4_K_M` in **`31.9 s`** (`147.7 s` before; `intent=recommend`, **`staged=1`** `VSync: On → Off`, `0` filtered).
* `cs2_full_setup` (1 turn, `fresh_install_comprehensive`): previously timed out at `360.1 s`; now completed cleanly with real `gemma4:12b-it-q4_K_M` in **`136.0 s`** (2 category-packed batches: Video `73.2 s`, Audio & Game `62.7 s`), staging **18** validated changes across **Video (8), Audio (3), and Game (7)** (`0` filtered, `valuesUnchanged = True`).
* `well_configured` (1 turn, `well_configured_competitive`): answered by `gemma4:12b-it-q4_K_M` in **`45.4 s`** (`228.1 s` before); validator caught `2` `no_op` hints cleanly and staged **`0`** forced changes (`valuesUnchanged = True`).
* `model_failure` (1 turn): unreachable Ollama (`9 ms`) triggered the labelled fallback immediately with **12** Video items staged (`valuesUnchanged = True`).

## 2. Original Windows research baseline (2026-11-21)

These baseline results describe the initial Windows prototype prior to the comprehensive pass. See the [current CI workflow](../.github/workflows/ci.yml) for CI commands (`windows-2025` & `macos-15`).

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

**Backend (`backend/tests/`, 107 tests)**
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
  full LangGraph run with a scripted model including a model-requested tool call, fast-path planner skip when grounded,
  post-tool round-limit short-circuit to compose, focused auto-stage behavior, stopword/substring-safe `search_settings`;
  prompt-injection attempt changes nothing; a request for changes without recommendations triggers exactly one repair;
  already-saved preferences are not re-suggested; malformed output → labelled fallback; timeout → fallback;
  single-flight + cancel; baseline has no chat; fallback explain/navigate/preference; cross-game ranking uses abstract
  preferences only (no sensitivity, CS2 values untouched); Relevant now hold rule and dismissal.
* `test_api.py` — health/catalog/state/search; manual change, stale revision, invalid value, history, undo over HTTP;
  CS2 explicit batch apply; adaptive gating; full chat → stage → apply → undo flow; context event + preference
  correction (only explicit sources accepted); reset backup, export/import round trip, `ai_only` reset, scenario path
  traversal rejected.
* `test_portability.py` — project-relative paths; no machine-specific paths in source; SQLite in a folder with spaces;
  Unicode round trip; UTF-8 catalogues without BOM; helper scripts run as subprocesses.
* `test_comprehensive_setup.py`, `test_crosshair_and_hud.py`, & `test_final_pass.py` — intent scope classification (`explain_only` precedence, `focused`, `category_optimization`, `full_game_setup`), low-weight `editorial` + `secondary-only` hint filtering when `include_minor=False`, idempotent auto-staging (`idx_proposals_run_autostage`), zero forced churn in `well_configured_competitive`, multi-batch partial-coverage deadline guard, personal/keybind safety enforcement, VALORANT 15-profile Crosshair CRUD + profile-switch Undo snapshot preservation + Riot `0;P;...` code parser + ADS/Sniper gating, CS2 HUD Edge `Done` immediate apply separate from Video pending drafts, DB v3 migration & History provenance + `restage_from_batch`, `personal_setup_facts` & conflict detection, `cross_game.py` curated mappings & `0.07 / 0.022` 360° hipfire conversion, and 4-trigger `Discover` + adaptive onboarding (`Scenarios 1–4`, `mark_checked`, `revisit_onboarding`).
* **Frontend (`menu.test.tsx`, `workspace.test.tsx`, 24 tests)** — A/B row parity, no AI affordances in baseline, Participant vs. Experimenter drawer gating, direct manual Pinned edits & CS2 Video pending-draft conflict modal, reactive SVG VALORANT crosshair preview, CS2 HUD Edge safezone inset math, dependent disabled rows, segmented/dropdown/slider/keybind/color controls, awaited `PreferenceChip` save with error/retry recovery, participant-safe progress labels (`participantStepLabel`), History provenance/restage, Workspace `Already aligned` / `Needs your decision`, `My Priorities` 3-section UI/facts, `Discover` `Mark checked`, and `Chat` cross-game comparison cards.
* **E2E (`frontend/e2e/journeys.spec.ts`, 22 specs)** — baseline manual edit/reload/history/undo, search, CS2 explicit Apply & presets, Participant chrome hiding, A/B parity across both games, auto-staged single & >12-item comprehensive setups, Pinned manual edits/locks/undo, locked-item blocking, preference confirmation with scope, detached `/?view=workspace` cross-window sync + exclusive main-window relocation & reload-free auto-restore on close, `Discover` (`Prepare for review`) cross-game transfer & reload hold + simulated context event, VALORANT Crosshair import/reload persistence, CS2 HUD Edge `Done` independence + `New` tab, History provenance + restage, `well_configured_competitive` zero-change aligned review, `My Priorities` facts, `valorant_onboarding_to_cs2` onboarding persistence + `VSync Off` companion follow-up, and grounded cross-game comparison (`0.35 → 1.11` with caveats).

## Not tested
* Linux, additional GPUs/hardware, or other Ollama versions/models (Windows 11 + RTX 4080 SUPER baseline and macOS `Darwin 27.0.0` `arm64` M4 are the verified environments).
* Real VALORANT or CS2 installations: the prototype never touches game files and measures no in-game FPS or latency.
* Human participants: no user study was run; comprehension, usability, and trust claims remain open (see [PARTICIPANT_PILOT.md](PARTICIPANT_PILOT.md)).
