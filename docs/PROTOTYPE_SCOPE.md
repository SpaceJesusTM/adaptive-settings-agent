# Prototype Scope Matrix (CSC2524 Formative Pilot Readiness)

This document defines the exact architectural boundary of **Adaptive Settings Agent** across four implementation tiers so paper claims and participant briefings stay strictly faithful to what the software does and does not do.

---

## Tier 1 — Implemented Faithfully (Genuine Interactive Mechanics)

- **Canonical Game Menus & A/B Spatial Invariance:** Identical menu tabs, subtabs, category sections, row order, control widgets (segmented, dropdown, slider, keybind, color, preset), prototype search (`Search settings`), dependency gating (`availability` rules), and single-write SQLite persistence across Condition A (Static Baseline) and Condition B (Adaptive) (`177` VALORANT settings, `138` CS2 settings).
- **Explicit User Authority, Staging, Apply & Atomic Undo:** Conversational recommendations are validated server-side (`backend/app/agent/validate.py`) and auto-staged into `Workspace → Changes` with zero changes to active setting values until explicit user **Apply selected changes**. Applies execute in an atomic `BEGIN IMMEDIATE` transaction (`store.py`), respect CS2 explicit-apply Video draft conflicts, and support full **Undo**.
- **Truthful Change History Provenance & Safe Restaging:** `change_batches` and `proposal_items` record authentic batch provenance (`Original request`, per-setting `why`/`tradeoff`/`basedOn`, whether edited before apply, live `Active` / `Changed since` / `Undone`, and current `(now ...)` values). Manual edits explicitly report *"Manual edit — no assistant rationale was recorded."* **Review & restage** creates a new editable proposal (`Restaged from history`) without touching live settings.
- **User Locks, Pins & Direct `Pinned` Manipulation:** Users can **Lock from AI** on any setting (enforced server-side before stage and apply) while keeping full manual override capability in the canonical menu and in `Workspace → Pinned`.
- **Exclusive Pop-Out Relocation (`/?view=workspace`):** Popping out the Adaptive Workspace synchronizes state over `BroadcastChannel` + `localStorage` heartbeat lease (`DETACHED_TTL_MS = 5000 ms`) and hides the docked Assistant/Workspace from the main window while providing **Focus** and **Dock here** / **Dock in main window** controls with automatic restoration when closed.
- **`My Priorities` System Understanding (`observations.py`, `profile.py`, `AssistantPanel.tsx`):** Separates **Current goal** (inferred naturally from chat optimization asks without manual forms), **What I've noticed automatically** (live observed controls distinguishing simulator defaults, scenario seeds, and manual edits, direction-matched tentative patterns, and remembered-vs-live discrepancies), and **What you've asked me to remember** (explicit user directives/confirmed preferences/facts with 1-click **Undo**, moving manual overrides under collapsible *Add or edit manually*).
- **Conservative Natural Memory & Semantic Freshness (`intent.py`, `validate.py`, `proposals.py`, `store.py`):** Distinguishes unambiguous memory instructions (*"Remember..."*, *"From now on..."*) from ambiguous preference chips and non-committal speculative remarks; flags stale pending/restaged drafts semantically (`consistent`, `outdated_goal`, `historical_preference`, `technically_stale`), distinguishes `Original request` vs `Request excerpt` in History, and caps reactive `Discover` at `4` items with unseen indicators, `Checked` vs `Applied ✓` states, and `no_longer_relevant` resolution cleanup on Undo.
- **Relevant-Setting Review Completeness:** Surfaces `Already aligned`, `Retained due to trade-off` (skipped to protect opposing user priorities), `Needs your decision`, and `Locked or unavailable` controls cleanly alongside proposed changes (plus a `>= 6`-item review confidence strip with *Keep medium/high only*) so Apply strictly commits real pending diffs.
- **Game-Specific Sub-UIs:** Reactive VALORANT 15-profile SVG Crosshair editor + validated Riot `0;P;...` share-code parser/serializer (`crosshair.py`), and CS2 `HUD Edge Positions` (`safezonex`/`safezoney`) with `(1 - Y)*50% / (1 - X)*50%` safezone geometry and independent **Done** commit.

---

## Tier 2 — Implemented as Structured Simulation

- **Game Setting Storage & Apply Effects:** Menu states live in SQLite (`setting_values`), not VALORANT (`GameUserSettings.ini`) or Counter-Strike 2 (`cs2_user_convars*.vcfg`) on disk. Changes produce immediate UI/preview/dependency transitions rather than launching or hooking live game executables.
- **Simulated PC Hardware Profile:** Scenarios attach deterministic hardware capabilities (`gpuVendor`, `ramGB`, `vramGB`, `displayRefreshHz`, `gsyncDisplay`) used for availability checks (e.g., locking *NVIDIA G-Sync* when `gsyncDisplay: false`) rather than probing host DXGI/Metal APIs.
- **Simulated Context Events & 4-Trigger `Discover` Rules:** Experimenter-triggered context events (`frame_drops`, `ranked_session`, `footsteps_hard_to_hear`, `unstable_connection`), companion rule follow-ups (`FOLLOWUP_RULES`, e.g., `VSync Off → check NVIDIA Reflex`), adaptive onboarding (Scenarios 1–4 persisted in `onboarding_state`), and priority ranking are deterministic rule evaluations—not real telemetry monitors or online bandit learning.
- **Curated Bidirectional Cross-Game Comparison Engine (`backend/app/domain/cross_game.py`):** Maps verified catalogue pairs between VALORANT and CS2 using explicit parsed direction (`SOURCE → TARGET`) regardless of active UI tab:
  - Team Push-to-Talk & Party/Voice channel architecture (`similar_with_differences`)
  - **Mouse Sensitivity (360° hipfire yaw):** Uses live observed game sensitivity or remembered notes with published degree/increment pitch math (`valSens * (0.07 / 0.022)`, e.g., VALORANT `0.35` → CS2 `≈ 1.11` at identical mouse DPI), surfaces mismatch callouts whenever a remembered fact disagrees with live settings, adds mandatory ADS/FOV caveats, and jumps cross-game directly to the target setting row (`targetNavigateGame`).
  - Utility / Ability vs Grenade slots & Use Object vs Inspect Weapon key discrepancies (`loose_analogy`)
  - Movement/Use/Ping keys, qualitative crosshair traits, and Video/Audio equivalents
- **Catalog Verification Mix:** CS2 (`138` settings) is extracted from local build `2000948` game files (`verified-game-files`). VALORANT (`177` settings) combines official Riot docs/screenshots (`56`), partially verified entries (`28`), and dated secondary docs (`93` `secondary-only` with `43` `rangeVerified: false` sliders and `19` inferred placements flagged transparently in the UI).

---

## Tier 3 — Intentionally Excluded from Automatic AI Action

To uphold human agency over ergonomics, muscle memory, and visual aesthetics (`DG3`, `DG4`), the following controls **cannot** be staged or applied by the AI (`validate.py`, `proposals.py`, `cross_game.py` reject them; surfaced only under `Needs your decision` or `Manual control` inspect cards with **Mark checked**):
- **Mouse Sensitivity & Zoom/Scoped Multipliers** (including across cross-game transfers)
- **Keybinds** (movement, Push-to-Talk, ping, abilities/grenades, equipment)
- **Video Quality Presets** (compound presets expand in manual CS2 Video menus only)
- **Crosshair Hex Colors & Custom Color Pickers** (`color` controls)
- **Unverified Slider Bounds** (`rangeVerified: false` in VALORANT)
- **User-Locked Settings** (`locks` table) and **Dependency-Unavailable Settings** (`availability`)

---

## Tier 4 — Out of Scope for Prototype

- **Direct OS / Live Game Integration:** No file-system writes to Steam/Riot directories, no Win32/macOS window overlay injection, and no game launches.
- **Hardware & Runtime Telemetry Capture:** No real FPS counters, frame-time graphs, network ping/packet-loss probes, or driver-panel inspection.
- **Unmodeled Game Screens:** VALORANT *Match* tab rules and CS2 *Controller / Steam Input* & *Chat Wheel* radial editors remain documented as out-of-scope (see [SETTINGS_COMPLETENESS_AUDIT.md](SETTINGS_COMPLETENESS_AUDIT.md)).
- **Remote Cloud / Multi-User Sync & Production Auth:** Single-participant local SQLite workspace; `Experimenter` toggle isolates facilitator controls cleanly for supervised sessions rather than acting as an adversarial security boundary.
- **Empirical Human-Study Results:** **Zero human participant sessions have been conducted**; usability, trust, comprehension, and cross-game learning outcomes remain untested hypotheses under [PARTICIPANT_PILOT.md](PARTICIPANT_PILOT.md).
