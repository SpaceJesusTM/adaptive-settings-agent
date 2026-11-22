# Participant Pilot Study Protocol (CSC2524)

**Status:** Study protocol ready; **zero participant sessions have been run** as of 2026-11-22. No participant data, preference ratings, or task timings exist yet.

## 1. Purpose & Design Constraints

This protocol evaluates two primary research questions (reflecting Ingesson & Riveiro, DIS 2026, and Findlater & McGrenere, CHI 2004 / IJHCS 2010):

1. **RQ1 (Navigation & Comprehension):** Does intent-responsive conversational guidance paired with an inspectable, non-rearranging Adaptive Workspace improve participants' **independent understanding** of competitive PC game settings compared with the static Baseline menu (which includes identical canonical search and undo)?
2. **RQ2 (Agency & Multi-Setting Review):** When setting up an unfamiliar game from a fresh install or transferring goals across games, do auto-staged multi-category plans in `Changes` and direct controls in `Pinned` preserve perceived user control without inducing blind rubber-stamping?

### Explicit N=1 Formative Pilot Caveat
If an initial **N=1 (or N=2–3) formative pilot** is conducted before a full class study, **report it strictly as a formative usability walk-through** to identify UI bottlenecks, prompt wording confusion, and timing issues. **Never frame N=1 observations as inferential evidence, statistical significance, or proof of condition superiority.**

## 2. Study Design

- **Structure:** Within-subject, counterbalanced A/B comparison across the two games (`VALORANT` and `CS2`) so every participant experiences both conditions without repeating identical items:
  - **Group 1:** Game 1 (`VALORANT`) in Condition **A (Baseline)** -> Game 2 (`CS2`) in Condition **B (Adaptive)**.
  - **Group 2:** Game 1 (`CS2`) in Condition **A (Baseline)** -> Game 2 (`VALORANT`) in Condition **B (Adaptive)**.
  *(Swap game-to-condition assignment between Group 3/4 if recruiting >= 4 participants.)*
- **Condition Parity:** Keep `Participant` view active (`Experimenter` toggle **OFF** during participant tasks) so Condition B participants see neither A/B labels nor debug traces. Use local AI (`gemma4:12b-it-q4_K_M`) consistently; record any automatic fallback triggers in the session log.
- **Session Duration:** ~25–30 minutes total per participant.

## 3. Core Tasks (Administered in Both Conditions)

Each participant completes three structured task types using starting scenario `fresh_install_comprehensive` (or `valorant_history_new_cs2` for Task 3 in CS2):

1. **Task 1 — Narrow / Single-Control Understanding & Adjustment (~3 min)**
   - *CS2 Prompt:* "Check how close the HUD sits to the screen edges and pull it slightly inward (`0.85` horizontal) without applying unrelated Video graphics changes."
   - *VALORANT Prompt:* "Locate the Minimap Vision Cones setting, verify what it changes, and adjust your primary crosshair center dot without touching mouse sensitivity."
2. **Task 2 — Comprehensive New-Install Setup (~8 min)**
   - Scenario: `fresh_install_comprehensive` (starting from high/blurry defaults + 60 FPS cap / V-Sync ON).
   - *Prompt:* "Configure this newly installed game for clear enemy visibility, low input latency, and team voice communication while keeping any setting you prefer unchanged."
   - In Condition B, observe whether the participant inspects category groups, edits or unchecks any staged items, locks/pins anything, or clicks `Show in settings` before pressing `Apply selected changes`.
3. **Task 3 — Cross-Game Transfer / Recovery (~5 min)**
   - Switch to the other game (`valorant_history_new_cs2` when ending on CS2, or simulated context event `Frame-rate dips` via Experimenter Drawer between trials).
   - Inspect `Discover` (in Condition B) or browse Video/Audio menus (in Condition A), decide which two settings to adjust, and use `Undo` on one unintended or experimental change.

## 4. Independent Understanding & Outcome Measures

**Critical Rule (Ingesson & Riveiro, DIS 2026):** Do **not** test comprehension while the participant reads the chat reply verbatim, and do **not** treat "user clicked Apply" as understanding.

- **Primary Measure — Independent Setting Comprehension (Scored Blind):**
  Immediately after finishing Task 2/3, close the chat/workspace (`Workspace` collapsed) and ask the participant to name **2–3 settings they changed (or left unchanged)** and answer two short prompts from memory / inspection of the canonical menu alone:
  1. *Function:* "What does this setting actually control?" (`0 = incorrect/blank`, `1 = partial`, `2 = accurate`)
  2. *Trade-off / Consequence:* "What downside or dependency does changing it introduce?" (`0 = none/incorrect`, `1 = partial`, `2 = accurate`)
- **Behavioral Trace Measures (automatically logged in SQLite):**
  - Time to completion per task, number of settings changed, count of `Show in settings` jumps (cross-reference with canonical menu vs blind workspace apply), per-item unchecks/edits before Apply, Rejects/Dismissals (with reason), Locks/Pins created, and Undo count.
- **Short Post-Condition Check:** 3 brief 7-point items (Perceived Control, Menu Predictability, Explanation Helpfulness) + 2 open-ended debrief prompts.

## 5. Concise Facilitator Script

1. **Setup (before participant sits down):** Verify `GET /api/model/status` reports `Connected local AI` (`gemma4:12b-it-q4_K_M`). Open **Experimenter -> Study controls**, run `Full reset` on `fresh_install_comprehensive`, select Condition A (or B per counterbalancing), then toggle **Experimenter OFF** so only the clean participant bar is visible.
2. **Briefing (~1 min):** *"This is a standalone settings simulator for VALORANT and CS2 — nothing here touches a real game or your PC. Please work as you normally would when tuning a game for competitive play, and think aloud briefly if anything feels unclear."*
3. **During tasks:** Do not coach participants toward `Show in settings`, `Pinned`, or `Changes`. Only intervene if a UI bug blocks progress or local inference stalls; note any assistance in the observation sheet.
4. **Post-task (~3 min):** Toggle **Experimenter ON**, run **Export session JSON** (save locally outside git), complete the blind understanding prompt answers before reviewing chat history together, then reset cleanly for the next condition.

## 6. Blank Observation Sheet (Copy Per Session)

```text
Participant ID: ______________   Date: ______________   Counterbalance Group: [ ] A-first (VAL->CS2)  [ ] B-first (CS2->VAL)
Mode Notes: [ ] Local AI (gemma4:12b-it-q4_K_M)   [ ] Fallback triggered? (Turn #: ____ Reason: _____________)

CONDITION A (BASELINE) — Game: ____________   Scenario: ____________________
- Task 1 (Narrow/HUD or Crosshair):  Start: _____  End: _____  Search used? Y/N  Undo used? Y/N
- Task 2 (Comprehensive setup):      Start: _____  End: _____  # Changes: ___   Confusion points: _______________________
- Task 3 (Transfer/Context):         Start: _____  End: _____  Video Pending Draft confusion? Y/N
- Blind Comprehension (pick 2 settings changed in Task 2; ask WITHOUT chat/notes):
  1) Setting: ______________________  Function (0-2): ___  Trade-off (0-2): ___  Notes: _________________________________
  2) Setting: ______________________  Function (0-2): ___  Trade-off (0-2): ___  Notes: _________________________________

CONDITION B (ADAPTIVE) — Game: ____________   Scenario: ____________________
- Task 1: Start: _____  End: _____  Used Chat / Pinned / Menu? __________  HUD Edge Done vs Apply clear? Y/N
- Task 2 (Auto-stage inspection): Start: _____  End: _____
  - Staged count: ___  Inspected categories? Y/N  Unchecked/edited any items? ___  Clicked "Show in settings"? ___
  - Opened "What it does & trade-offs"? ___  Opened "What I checked"? ___  Pinned/Locked any rows? ___
  - Rubber-stamp risk observed? Y/N  Detached ?view=workspace used? Y/N
- Task 3 (`Discover`): Prepared from Discover? ___  Dismissed any cards? ___  Used Pinned direct edit? Y/N
- Blind Comprehension (pick 2 settings changed in Task 2; close Workspace & Chat first):
  1) Setting: ______________________  Function (0-2): ___  Trade-off (0-2): ___  Notes: _________________________________
  2) Setting: ______________________  Function (0-2): ___  Trade-off (0-2): ___  Notes: _________________________________

DEBRIEF & EXPORT
- Export JSON filename (stored locally, not committed): ______________________________
- Post-condition Likert (1=Strongly Disagree .. 7=Strongly Agree):
  Baseline — Control: ___  Predictable menu: ___  Understood trade-offs: ___
  Adaptive — Control: ___  Predictable menu: ___  Understood trade-offs: ___  Workspace clutter (1=low,7=high): ___
- Top friction / bug / surprise reported by participant:
  _________________________________________________________________________________________________________________
```
