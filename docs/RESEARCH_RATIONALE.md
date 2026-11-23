# Research Rationale & Architecture Boundaries

This document summarizes the CSC2524 research rationale behind `Adaptive Settings Agent`, focusing on the mechanisms introduced in the comprehensive UX and settings pass and drawing an explicit line between **Track A (verified system properties)** and **Track B (human-participant claims not yet tested)**.

## 1. Research Framing

Complex PC competitive games expose 100+ interdependent settings whose effects and trade-offs are opaque to novices and time-consuming for experienced players configuring a new title or new PC. Prior adaptive UI research demonstrates two recurring failure modes when systems adapt aggressively:

1. **Spatial instability & feature blindness** (Findlater & McGrenere, CHI 2004 & IJHCS 2010): rearranging controls or burying them in dynamic shortcuts speeds immediate hits at the cost of user predictability and awareness of unpromoted controls.
2. **Low-agency automation vs. cognitive overload** (Kim et al., IUI 2026; Alves et al., CHI 2026; Ingesson & Riveiro, DIS 2026): unsolicited changes erode trust, while dumping verbose explanations and raw telemetry overwhelms users whose demand for explanations is goal- and difficulty-dependent.

Our prototype explores **adaptive guidance without menu rearrangement**: keeping the canonical VALORANT (`177` settings) and CS2 (`138` settings) menus spatially invariant across A/B conditions while channeling conversational recommendations, direct pinned controls, and proactive cross-game suggestions through an inspectable Adaptive Workspace.

## 2. Core Architectural Pillars

### 2.1 Intent-Responsive Scope & Deterministic Coverage Auditing
- **Classifier (`backend/app/agent/scope.py`):** Distinguishes five scopes (`explain_only`, `focused`, `category_optimization`, `broad_optimization`, `full_game_setup`), respecting `explain_only` precedence (e.g., `"What does VSync do?"` never triggers recommendations even with overrides).
- **Coverage audit (`backend/app/domain/planner.py`):** Computes eligible, already-optimal, AI-locked, manual-only, already-staged, and condition-unavailable settings per category before invoking the LLM, filtering low-weight `secondary-only`/`editorial` tweaks when `include_minor` is false. When the user is already in a competitive state (`well_configured_competitive`), eligible targets drop to zero across all categories, preventing forced suggestions.
- **Category batching (`backend/app/agent/graph.py`):** When broad/full-setup asks exceed `BATCH_SIZE` (`12`) eligible candidates, the agent packs adjacent category slices up to `12` items and composes sequentially within `AGENT_DEADLINE_S` (`MAX_PROPOSAL_ITEMS=60`, using a compact `BatchDraft` schema on secondary batches), attaches structured `plan` metadata, and explicitly flags partial coverage if the deadline is reached.

### 2.2 Idempotent Auto-Staging Without Auto-Apply
- Previously, participants asked in chat, then had to click `Stage` before inspecting editable diffs. Now, every validated recommendation batch from a chat turn is automatically staged into `Changes` inside the same database write transaction (`runner.py` -> `proposals.auto_stage_for_run`) keyed by a unique partial index (`idx_proposals_run_autostage`).
- **Hard invariant preserved:** Auto-staging touches **zero** active setting values. Values change only upon explicit user `Apply selected changes` (which validates revisions, locks, dependencies, and CS2 pending video conflicts inside an atomic SQLite transaction).
- Dismissals (`reject`) record structured feedback and never alter settings; `Undo` reverts committed apply batches cleanly.

### 2.3 Unified Adaptive Workspace (`Changes`, `Pinned`, `Discover`) & Detachable View
- **`Changes`:** Renders staged plans grouped cleanly by menu category with `From → To` previews, per-item selection checkboxes, inline value editing, locks, and `Show in settings`.
- **`Pinned`:** Gives users direct manual `SettingControl` access to their chosen settings right beside chat, saving directly without passing through the AI proposal queue—and honoring user authority even when a setting is `Locked from AI`. For CS2 explicit-apply Video settings (`applyMode === "explicit"`), conflicting unapplied Video drafts surface an explicit user confirmation modal (`Apply all pending` vs `Save just this`) rather than silently mutating drafts.
- **`Discover`:** Holds deterministic rule-based suggestions (including simulated hardware/performance context events and cross-game abstract-dimension transfers, never copying numeric sensitivities or keybinds) until the user opens/refreshes or prepares a card for review (`Prepare for review`).
- **Detachable synchronization (`frontend/src/lib/sync.ts`):** Opening `/?view=workspace` launches an independent synchronized window/tab over `BroadcastChannel` + `storage` + focus events so the workspace can sit beside the canonical menu on smaller viewports or separate screens.

### 2.4 Participant UX vs. Experimenter Diagnostics
- `StudyBar` defaults to **Participant mode**: `condition`, model tags (`gemma4:12b-it-q4_K_M`), `Study controls` (scenario resets, simulated events, fallback toggle, export), and the `Trace` tab are hidden inside `ExperimenterDrawer` behind an explicit `Experimenter` toggle.
- Assistant chat replies remain compact (`Why` + structured summary + `Review N changes` button + collapsed `What I checked`), preventing raw tool call logs from cluttering the participant reading path.

### 2.5 Final HCI Pass Additions (Provenance, Personalization Hierarchy, Cross-Game Grounding & Exclusive Pop-Out)
- **Truthful History Provenance & Non-Silent Restage (`store.py`, `proposals.py`, `HistoryDrawer.tsx`):** Applied batches surface authentic recorded `Original request` and expandable `Why suggested & trade-offs` (plus live `Active` / `Changed since` / `Undone` states and `(now ...)` overrides). Manual edits explicitly disclose missing assistant rationale rather than inventing post-hoc stories. **Review & restage** builds a fresh editable draft in `Changes` without silent writes.
- **Relevant-Setting Review Beyond Edits (`planner.py`, `AdaptiveWorkspace.tsx`, `Chat.tsx`):** Actionable diffs sit alongside structured `Already aligned`, `Needs your decision`, and `Locked or unavailable` lists—communicating restraint and complete review coverage while strictly scoping Apply checkboxes to real proposed changes.
- **Exclusive Pop-Out Relocation (`App.tsx`, `StudyBar.tsx`, `StandaloneWorkspace.tsx`, `sync.ts`):** When `/?view=workspace` connects, a heartbeat-leased `BroadcastChannel` state hides the docked Assistant/Workspace in the main window (preventing duplicated/conflicting review panels) and exposes `Focus` / `Dock here`, restoring automatically on close without reload.
- **`My Priorities` 3-Section Split & Confirmed Personal Facts (`profile.py`, `AssistantPanel.tsx`):** Separates (1) Current session goal + automatic goal-vs-priority conflict notices, (2) General priorities (session vs durable across games), and (3) Explicitly confirmed personal setup facts (such as Push-to-Talk key or sensitivity, never auto-applied).
- **4-Trigger `Discover` & Curated Cross-Game Helper (`recommender.py`, `cross_game.py`):** Groups proactive inspect/change cards across simulated context events, companion follow-ups (e.g., `VSync Off → NVIDIA Reflex`), adaptive first-time game onboarding (Scenarios 1–4 with `Mark checked` and `Revisit first-time checks`), and saved priorities. Cross-game comparisons answer equivalency and `0.07 / 0.022` 360° hipfire yaw questions with mandatory FOV/ADS caveats and zero automatic sensitivity/keybind copying.

## 3. Track A (Verified Here) vs. Track B (Human Evaluation Required)

| Track | Scope of Evidence | What Can Be Claimed Now | What Cannot Be Claimed Yet |
|---|---|---|---|
| **Track A: System & Technical Verification** | Backend unit/integration (`pytest`), frontend unit (`vitest`), Playwright E2E (`journeys.spec.ts`), portability checks (`test_portability.py`), static/build verification, and local `gemma4:12b-it-q4_K_M` live evaluation (`smoke_check.py`, `run_model_eval.py`). | Strict A/B DOM row/order parity; zero auto-applied values on auto-stage/reject/prompt-injection; lock & keybind/sensitivity non-proposability enforcement; Riot `0;P;...` parser & CS2 `safezonex`/`safezoney` preview math accuracy; cross-window sync; grounded provenance labels and schema-validated local LLM responses. | Whether participants actually find settings faster, understand trade-offs better, trust the agent appropriately, or prefer docked vs. detached workspaces. |
| **Track B: Human Participant Study (Protocol Only)** | Within-subject counterbalanced A/B protocol defined in [PARTICIPANT_PILOT.md](PARTICIPANT_PILOT.md). | Study readiness: isolated condition switching, synthetic scenarios, exportable SQLite action traces, and independent comprehension scoring rubric exist in the codebase. | Any statistical or qualitative claim about human comprehension, NASA-TLX/UMUX usability, trust, or long-term learning effects. |
