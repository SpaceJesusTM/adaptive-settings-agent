# Next Pass Progress Log (`feat/comprehensive-ux-settings-pass`)

Living checklist for the research, UX consolidation, adaptive-scope planning, missing settings sweep, and macOS Ollama verification pass.

## Baseline (before edits, commit `ff6874e`)

- **Branch created:** `feat/comprehensive-ux-settings-pass` from `main` (`ff6874e`)
- **Host:** macOS `27.0` (`arm64` Apple Silicon), 24 GB unified memory, 42 GiB free disk, Python `3.11.6`, Node `v22.20.0`, Ollama `0.40.15`
- **Baseline automated checks (2026-11-22):**
  - Backend `pytest`: **85/85 passed** (`2.09 s`)
  - Frontend `tsc --noEmit`: **clean**
  - Frontend `vitest`: **10/10 passed** (`589 ms`)
  - Playwright E2E (`PW_CHANNEL=chrome`, `e2e/journeys.spec.ts`): **12/12 passed** (`14.3 s`)
- **Baseline Ollama diagnosis on Mac:**
  - Ollama service reachable at `http://127.0.0.1:11434` (`0.40.15`), but `.env` had `OLLAMA_MODEL=` empty and `gemma4:12b-it-q4_K_M` was not installed in local Ollama (`ollama list` showed only `qwen2.5-coder:7b`, `qwen3.5:9b-q4_K_M`, `qwen3.5:2b-q4_K_M`, `qwen3.5:4b-q4_K_M`).

## Phase Checklist

| Phase | Goal | Status | Notes |
|---|---|---|---|
| Phase 0 | Branch, baseline test freeze, progress log | Complete | Baseline suites verified green on macOS (`ff6874e`) |
| Phase 1 | Mac Ollama (`gemma4:12b-it-q4_K_M`) pull, `.env`, live structured + chat test | Complete | Pulled exact tag `gemma4:12b-it-q4_K_M` (`8.0 GB`, `Q4_K_M`); `.env` configured (`OLLAMA_TIMEOUT=180`, `AGENT_DEADLINE_S=360`); `smoke_check.py --backend --real-model` 9/9 OK; live `/api/chat` (`task-339`) succeeded in `114.9s` (`provenance.source == "ai"`, `stagedProposalId` created, `values_unchanged == True`) |
| Phase 2 | Backend: DB v2 migration, scope classifier, coverage planner, idempotent auto-stage, expanded proposals | Complete | Schema v2 + `scope.py` + `planner.py` + `proposals.py` (`MAX_PROPOSAL_ITEMS=60`, `auto_stage_for_run`) + compacted `prompts.py` + category-batched `graph.py` + `fallback_turn` + `runner.py` auto-stage inside `write_tx`; `pytest` 85/85 passed + live Gemma 4 test verified |
| Phase 3 | Settings completeness: Crosshair profiles, color domain, HUD Edge immediate Done, VALORANT & CS2 catalogues, scenarios | Complete | `valorant.json` (177 settings), `cs2.json` (138 settings), `crosshair.py` (15 profiles + validated `0;P;...` code parser/serializer), `fresh_install_comprehensive` & `well_configured_competitive` scenarios, regenerated `CATALOG_REPORT.md` (315 settings), `pytest` 86/86 passed |
| Phase 4 | Frontend: Participant/Experimenter split, simplified chat, unified Adaptive Workspace (`Changes`/`Pinned`/`Discover`), detachable `?view=workspace`, new game editors | Complete | Participant-first `StudyBar` + `ExperimenterDrawer`, simplified `Chat.tsx` (`Review N changes`, `What I checked`, scope pill), `<AdaptiveWorkspace>` (`Changes` grouped by category, `Pinned` direct manual save + undo + CS2 `pendingVideo` guard, `Discover`), `<StandaloneWorkspace>` w/ `BroadcastChannel` sync, VALORANT Crosshair Bar/Preview, CS2 HUD Edge live editor & `New` tab; `npm run build` + `vitest` 10/10 passed |
| Phase 5 | Comprehensive backend/unit/E2E tests, real Gemma 4 eval, research literature & completeness docs | Complete | Added `test_comprehensive_setup.py`, `test_crosshair_and_hud.py`, `workspace.test.tsx`, 17 Playwright E2E specs, 8 Playwright screenshots, updated `run_model_eval.py`, and created `NEXT_PASS_DESIGN_AUDIT.md`, `RESEARCH_RATIONALE.md`, `PARTICIPANT_PILOT.md`, `SETTINGS_COMPLETENESS_AUDIT.md` |
| Phase 6 | Full regression suites, live Gemma 4 eval, visual browser verification, PR preparation | Complete | Verified `vitest` (15/15), `PW_CHANNEL=chrome` E2E (17/17) & screenshots (2/2), `smoke_check.py --real-model` (8/8), live `gemma4:12b-it-q4_K_M` eval (`20261122-143214`: 7 AI turns + 2 labelled fallbacks, `valuesUnchanged: True`), and T3 browser inspection at `1440×900` & `1280×720` (fixed `StudyBar` shrink, top-right toasts, select arrow, sticky Workspace Apply bar) |
