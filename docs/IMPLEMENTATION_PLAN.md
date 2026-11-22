# Implementation plan — *Adapting Without Rearranging*

CSC2524 (University of Toronto) course prototype. Independent HCI + AI research project; **not** an AMD/NPU demo.
Specification: `CSC2524_Claude_Opus_5_5_Implementation_Prompt_CrossPlatform_Gemma14B_Q4.md` (this folder).
Resumable status lives in [`PROGRESS.md`](PROGRESS.md); decisions in [`DECISIONS.md`](DECISIONS.md).

## Phase checklist

| Phase | Scope | Status |
|---|---|---|
| 0 | Audit workspace/toolchains/model, plan, decision log, limitations | done |
| 1 | Research current VALORANT + CS2 menus; `GAME_SETTINGS_AUDIT.md`; versioned catalogues (30+ verified settings/game); catalogue validation tests | done (VALORANT 54 officially confirmed of 74; CS2 121 from game files) |
| 2 | Baseline: game switch, authentic tab/subtab layouts, manual widgets, search → canonical location, validation, persistence | done |
| 3 | Safe state: schema bootstrap/migrations, revisions, proposals, approval, locks, pins, history, undo, reset/seed; negative + concurrency tests | done |
| 4 | Local model agent: exact-tag health check, bounded LangGraph workflow, grounded read tools, structured output, validation, trace, timeout/cancel, labelled offline fallback; ≥1 real request | done (real-model evaluation logged) |
| 5 | Adaptive UX: Relevant Now (hold rule), goal chat, layered explanations, highlight of original rows, staged diff/edit/apply/reject, feedback, preference correction, disable adaptation, cross-game transfer | done |
| 6 | Scenario fixtures/replays, evidence logs, acceptance scripts, screenshots, demo script, paper notes, test summary | done |
| 7 | Portability review (Windows verified, macOS documented/untested), cleanup, final screenshots, handoff | done (macOS untested) |

## Architecture (separation of concerns required by spec §3)

```
frontend (React + TS + Vite)            backend (FastAPI + Pydantic)                 local runtime
┌───────────────────────────┐  /api   ┌──────────────────────────────────────────┐   ┌────────────┐
│ (f) UI rendering           │ ─────▶ │ (a) catalogue loader + validator (JSON)   │   │  Ollama    │
│  game shells (VAL / CS2)   │        │ (b) value store, revisions, history, undo │   │  exact tag │
│  shared setting widgets    │        │ (c) profile: durable prefs vs session goal│   │  from env  │
│  adaptive layer (cond. B)  │        │ (d) agent: LangGraph, read-only tools ────┼──▶│ (server-   │
└───────────────────────────┘        │ (e) deterministic validation + approval   │   │  side only)│
                                      │     SQLite (data/local/app.db)            │   └────────────┘
                                      └──────────────────────────────────────────┘
```

* **(a) Catalogue** – one canonical, versioned JSON file per game in `data/catalogs/`, validated by Pydantic at load and by tests. Every setting carries provenance (`sourceURL`, `sourceDate`, `verificationStatus`).
* **(b) Values/revisions** – per-setting revision + per-game revision; every mutation (manual, approved proposal, undo, reset) goes through **one** function (`apply_changes`) inside a `BEGIN IMMEDIATE` transaction.
* **(c) Profile** – abstract preference dimensions shared across games (e.g. `input_latency`, `visibility`); values and control IDs are never shared.
* **(d) Agent** – can only *read* and *propose*. It has no write tool; proposals are data.
* **(e) Policy** – allowlist, type/domain, availability, locks, revision checks, all-or-nothing bundle apply, idempotency keys.
* **(f) UI** – the canonical All Settings menu is identical in both conditions; condition B adds panels around it and never re-orders rows.

## Acceptance criteria (from spec §10, tracked in PROGRESS.md)

1. Self-contained in `csc2524_prototype`; Windows run verified; macOS instructions present (unverified unless actually run).
2. Two recognisably different, source-audited game menus.
3. Interactive controls with stable paths and valid domains across all main areas.
4. Baseline has no AI; adaptive = same menu + assistance.
5. Browse, search, change, revert in either condition.
6. Exact configured local model selects real settings, explains, proposes valid changes; fallback explicitly labelled.
7. Recommendations highlight the existing row; rows never move.
8. No value changes before approval; locks and invalid values rejected regardless of model output.
9. Edit/stage/reject/apply bundle; history; safe undo; restart-persistent.
10. Pins, dismissals, corrections, transient vs durable preferences coherent.
11. VALORANT → CS2 carries high-level preferences only.
12. Automated tests for the no-unauthorised-change invariant and crucial flows (actual results reported).
13. Reproducible demo; same-state baseline/adaptive screenshots; simulated elements labelled.
14. Final summary with counts, commands, model tag/quantisation, tests, gaps.
15. Nothing outside `csc2524_prototype` changed (except the user-approved Ollama model pull); no Git/GitHub actions.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Menu facts drift (2026 patches) / sources disagree | Prefer official Riot/Valve sources; record date + verification level per setting; omit or mark unverified rather than guess. |
| Model is 12B not "14B" as the user labelled it | User explicitly approved `gemma4:12b-it-q4_K_M` (see DECISIONS D-01); documented in `MODEL_SETUP.md`. |
| Local inference latency (multi-second) | Background run + polling with progress steps, cancel button, per-call and overall timeouts, bounded steps. |
| Model emits invalid IDs/values or ignores locks | Server-side validator drops/flags items; apply path re-validates; tests cover adversarial model output. |
| Prompt injection via text/metadata | Data is passed as JSON in delimited blocks; model has no write tools; validator is authoritative. |
| Windows/macOS divergence | `pathlib`, Python helper scripts instead of shell scripts, no shell-specific npm scripts, portability tests. |
| Visual fidelity limited by inability to use proprietary assets | Original CSS/SVG approximations of layout, density, colour and typography; documented deliberate differences. |
