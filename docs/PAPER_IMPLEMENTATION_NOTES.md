# Implementation notes for the paper (verified facts only)

*Adapting Without Rearranging: Conversational Guidance for Complex Settings* — CSC2524, University of Toronto.
Everything below was implemented and checked in this repository on 2026-11-21. **No user study was conducted**; no
participant data exists. Numbers come from automated tests and logged runs on one Windows PC.

## System overview

```mermaid
flowchart LR
  subgraph Browser["Browser (React + TypeScript)"]
    M["Canonical game menu<br/>(VALORANT or CS2 shell)"]
    A["Adaptive layer (condition B only)<br/>Relevant now · chat · review tray · pins/locks · preferences"]
  end
  subgraph Backend["FastAPI backend"]
    C["Versioned catalogues<br/>(195 settings, provenance)"]
    S["Store: values, revisions,<br/>history/undo (single write path)"]
    P["Proposal engine<br/>(stage → revalidate → apply)"]
    R["Profile + deterministic recommender<br/>(goals, durable prefs, hold rule)"]
    G["LangGraph turn: context → read-only tools<br/>→ JSON-schema answer → validator → (repair) → fallback"]
  end
  O[("Ollama<br/>gemma4:12b-it-q4_K_M")]
  M -- "manual change" --> S
  A -- "goal / question" --> G
  G -- "read only" --> C & S & R
  G <-- "server-side only" --> O
  G -- "validated suggestions" --> A
  A -- "user stages" --> P
  P -- "explicit Apply" --> S
  R --> A
```

* **Testbed:** two simulated PC settings menus. VALORANT: 74 settings (54 confirmed by Riot documentation or Riot-
  published menu screenshots, 6 partially, 14 secondary-only and marked); CS2: 121 settings, all taken from the CS2
  client files of build 2000948 (2026-11-20). Both menus share one typed settings engine and differ in layout and
  styling (VALORANT: centred tabs, banded rows, segmented On/Off; CS2: top navigation, dropdown rows, split Advanced
  Video with native Apply/Discard).
* **Conditions:** A = static baseline (full menu, manual change, prototype search, history/undo). B = the same menu plus
  augmentation. Automated tests assert identical rows and order in A and B and no AI affordances in A.

## Design goals → mechanisms

| Goal | Mechanism (implemented) |
|---|---|
| **DG1 Stable access** | Canonical catalogue order is never changed; recommendations link to the *existing* row (temporary outline highlight); pins are shortcuts, not copies; search jumps to the canonical location. |
| **DG2 Understanding** | Every card separates **What it does** (verified catalogue text, source-labelled: Valve tooltip / Riot doc / editorial) from **Why this may help your goal** (model or rule rationale, origin-labelled), plus trade-offs, verification level and a *Why this?* evidence panel. Unverifiable numeric performance claims are removed by the validator. |
| **DG3 Agency** | Suggestions → explicit **Stage** → editable review tray → **Apply selected changes**; reject/dismiss with feedback; locks (“Locked from AI changes”) enforced at staging and apply; history with source, before/after and proposal id; undo; adaptation can be switched off. |
| **DG4 Continuity & context** | Session goals (transient, per game) vs durable preferences (explicit, cross-game, with evidence); simulated context events (labelled); cross-game transfer of *abstract* preferences only — CS2 suggestions cite “your saved preference … in VALORANT”; sensitivity and keybinds are never proposable. |

## Authority boundary (the safety property)

* The model has **no write tools**. Read-only tools: `get_current_ui_state`, `list_settings`, `get_setting_details`,
  `search_settings`, `get_user_preferences`, `get_change_history`.
* Its structured answer is validated against the selected game's allowlist, proposability, locks, value domain (exact
  options / on-grid numbers), availability on the simulated PC, no-ops and duplicates; IDs or labels from the other game
  are rejected. Baselines are captured server-side when the user stages.
* Apply is all-or-nothing in one SQLite `BEGIN IMMEDIATE` transaction with per-setting revision checks and idempotency
  keys; conflicts return 409 with per-item reasons. Tests: 4 simultaneous applies → exactly 1 succeeds; a bundle with
  one item locked after staging applies nothing; a prompt-injection request changes nothing.

## Measured results (automated; not user outcomes)

* Tests: backend **62/62**, frontend unit **10/10**, Playwright end-to-end **12/12** (5 consecutive runs), smoke
  check 9/9.
* Real local model (`gemma4:12b-it-q4_K_M`, RTX 4080 SUPER 16 GB, think off), 10 goal cases / 13 turns: 12 turns
  answered by the model with the intended intent (recommend / explain / preference / navigate / clarify), 1 deliberate
  model-failure turn answered by the labelled fallback; latency **3.1–8.0 s (median 5.0 s)** per turn after warm-up
  (cold load ≈ 20 s); 12/12 schema-valid answers; the assistant changed **0** values and auto-created **0** proposals.
* Reasoning mode on: median 13.2 s and one answer failed to complete valid JSON within 6 000 tokens → kept off.
* Prompt iteration with the real model was necessary: the first version produced clarifying questions instead of
  recommendations for clear goals (logged in `docs/evidence/model_runs/`).

## Limitations (state them in the paper)

* Simulation only: no game files are read or written; no frame-rate or latency effect is measured. Suggestions are
  grounded in documentation, not in measurements of the user's PC (the PC profile is simulated).
* VALORANT has no public machine-readable settings source; 14 settings rely on secondary sources and 19 section
  placements after Patch 12.07 are inferred. The VALORANT crosshair editor is not simulated.
* One model on one Windows PC; macOS instructions are untested. Model outputs vary between runs; the validator and
  the single repair round bound, but do not eliminate, this variability.
* Relevant-now ranking is a transparent rule (goal tags × weights), not learned; cross-game transfer is limited to the
  nine abstract preference dimensions encoded in the catalogues.
* No participants: claims about comprehension, usability or trust are **not** established by this work.

## Proposed first human evaluation (not conducted)

Within-subjects comparison of A vs B on the same game, catalogue and starting state: participants complete
goal-based tasks involving unfamiliar settings (e.g. “reduce input latency”, “see players better in dark areas”).
Primary measure: **independent understanding** of the changed settings (post-task explanation of function and
trade-off, scored blind). Secondary: task success and time, number of unintended changes, use and acceptance of
undo/lock/reject, perceived control and trust (questionnaires), and transfer to the second game. The current build
already logs the needed traces (history sources, proposal decisions, run traces, dismissals with reasons).
