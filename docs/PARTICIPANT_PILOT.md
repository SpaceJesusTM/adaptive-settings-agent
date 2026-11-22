# Participant Pilot Study Protocol (CSC2524)

**Status:** Protocol ready for formative piloting; **zero human participant sessions have been conducted** as of 2026-11-22. No human timings, comprehension scores, usability ratings, or preference outcomes exist yet.

## 1. Purpose & Research Questions

This protocol evaluates two exploratory research questions for *Adapting Without Rearranging: Conversational Guidance for Complex Settings*, grounded in Findlater & McGrenere (CHI 2004, IJHCS 2010), Bunt et al. (IUI 2007), Todi et al. (CHI 2021), Kim et al. (IUI 2026), Alves et al. (CHI 2026), and **Ingesson & Riveiro (DIS 2026)**:

1. **RQ1 (Navigation & Independent Comprehension):** Does intent-responsive conversational guidance paired with an inspectable, non-rearranging Adaptive Workspace improve participants' **independent understanding** of unfamiliar competitive PC game settings compared with an identical canonical static menu (which retains equal search, preview, and undo)?
2. **RQ2 (Agency, Rubber-Stamping & Multi-Setting Review):** On comprehensive fresh-install setups and cross-game transitions, do category-grouped auto-staged `Changes` plans and direct manual `Pinned` controls support user authority without inducing blind approval ("rubber-stamping") of large recommendation batches?

> [!IMPORTANT]
> **N=1 / Small Formative Pilot Boundary:** If an N=1–3 formative pilot is run prior to a formal study, treat it strictly as a **formative usability & instrument walkthrough** (identifying UI friction, prompt ambiguity, latency bottlenecks, and ceiling/floor effects in comprehension scoring). Never report N=1–3 notes as statistical evidence or proof of condition superiority.

---

## 2. Study Design, Confounds & Counterbalancing

### 2.1 Within-Subject 2×2 Counterbalanced Assignment
To prevent item memorization across Condition A (Baseline) and Condition B (Adaptive) while preventing Condition Order and Game Assignment from confounding each other, assign participants across **four counterbalanced cells**:

| Cell | Block 1 (Condition + Game) | Block 2 (Condition + Game) | Purpose |
|---|---|---|---|
| **G1** | **A (Baseline)** — VALORANT | **B (Adaptive)** — CS2 | A first; VALORANT→CS2 |
| **G2** | **A (Baseline)** — CS2 | **B (Adaptive)** — VALORANT | A first; CS2→VALORANT |
| **G3** | **B (Adaptive)** — VALORANT | **A (Baseline)** — CS2 | B first; VALORANT→CS2 |
| **G4** | **B (Adaptive)** — CS2 | **A (Baseline)** — VALORANT | B first; CS2→VALORANT |

* **Optional Block 3 (Cross-Game Transfer & Recovery, Adaptive Only):** Run *after* completing and scoring Block 1 and Block 2 (`valorant_history_new_cs2` in CS2 or simulated `frame_drops` context event), so cross-game transfer practice never contaminates primary A-vs-B parity comparisons.

### 2.2 Condition Parity & Disclosed Game-Menu Asymmetry Confounds
* **Prototype-level parity (preserved by code & tests):** Both A and B share identical setting IDs, canonical tab/section locations, row order, prototype search, CS2 explicit Video Apply/Discard semantics, VALORANT 15-profile Crosshair editor, CS2 HUD Edge Positions (`Done` immediate save), manual change validation, and atomic `Undo`.
* **Disclosed Adaptive Intervention:** Condition B adds chat guidance, auto-staged `Changes`, `Pinned` direct manual editing (and AI locks), and `Discover` (inside docked/detached Adaptive Workspace). Keep **Experimenter** toggled **OFF** (`Participant` mode) throughout participant tasks so condition tags (`A · Static baseline` / `B · Adaptive`), `Study controls`, `Trace`, and raw model IDs stay hidden.
* **Known Game-Level Confound (Must Analyze Across Counterbalanced Cells):**
  1. **Catalogue size & documentation texture:** VALORANT has `177` rows (`59` AI-proposable, immediate saves, Crosshair profiles, `93` secondary-only items with † badges), whereas CS2 has `138` game-file-verified rows (`93` AI-proposable, deferred explicit `Apply Changes` on Video settings, `HUD Edge Positions`, and `New` tab).
  2. **Task difficulty calibration:** Pairing `fresh_install_comprehensive` across both games keeps the number of actionable high- and medium-impact performance/clarity targets roughly comparable (`>= 12` meaningful changes across Video, Audio, and General/Game), while G1–G4 counterbalancing statistically separates Game differences from A/B condition differences in larger samples. In N=1–3 pilots, note game-specific friction (especially CS2 explicit `Apply Changes` vs immediate save) explicitly rather than averaging over it.

---

## 3. Core Tasks (~25–30 min Session)

Seed every main block from `fresh_install_comprehensive` via **Experimenter → Study controls → Full reset** (which starts with V-Sync On, blurry/high defaults, capped FPS, and unoptimized voice/HUD settings).

### Task 1 — Narrow Precision Control + Dependency Verification (~3 min)
* **VALORANT:** *"Find Minimap Vision Cones, explain what it controls, check Rotate/Fixed Orientation dependency, and enable a Cyan Primary Crosshair with a small center dot without altering Mouse Sensitivity."*
* **CS2:** *"Check how far HUD elements sit from the screen edges, move HUD Edge Positions inward horizontally to `0.85` and save with `Done`, and inspect one Advanced Video pacing option without accidentally discarding other changes."*
* *Equivalence note:* Both tasks require locating an unfamiliar setting, navigating a multi-layer or modal game-specific control (Crosshair subtabs/color custom vs HUD Edge popup + `Done` isolation), and checking dependency/save scope.

### Task 2 — Comprehensive Competitive & Clarity Setup (~8–10 min)
* **Same Goal Brief (both games):** *"Imagine you just installed this game on a competitive gaming laptop/PC. Configure it for smoother competitive frame rate, clear enemy visibility, low input latency, and clean team voice communication—while leaving personal mouse sensitivity and keybinds to your own preference."*
* In Condition A: participant browses/searches menus and adjusts settings directly.
* In Condition B: participant asks the assistant (using either narrow/category follow-ups or a comprehensive setup prompt), inspects `Workspace → Changes`, selectively unchecks/edits/locks items or clicks `Show in settings` to inspect canonical rows, and explicitly chooses what to **Apply**.

### Task 3 — Post-Block Recovery / Cross-Game Transfer (~5 min)
* **Condition Parity Check (end of Block 1 & Block 2):** Ask participant to locate and **Undo** one recent setting batch they decide wasn't worth the trade-off.
* **Block 3 Cross-Game Add-on (after primary blocks, Condition B only):** Switch to `valorant_history_new_cs2` in CS2 -> inspect **Workspace → Discover** cards referencing VALORANT priorities -> dismiss one card with a reason -> click **Prepare for review** on another -> test pinning one setting in **Workspace → Pinned** (and optionally opening `?view=workspace`).

---

## 4. Independent Understanding, Rubber-Stamping & Latency Rules

### 4.1 Independent Setting Comprehension (Closed-Book)
Following **Ingesson & Riveiro (DIS 2026)**, passive access to collapsible explanations in chat does **not** prove comprehension. Immediately after Task 2 ends in *each* condition:
1. **Collapse Workspace & Chat** (`Workspace` closed; Condition B chat scrolled away or hidden) so participants cannot read off assistant text verbatim. You may leave only the canonical game menu open if asking them to point out settings, or ask closed-book first and verify on the menu afterward.
2. Select **3 concrete target settings** from their session trace:
   - *(Item 1)* One high-impact Video setting they changed (e.g., `VSync` / `V-Sync`, `NVIDIA Reflex`, or `Anti-Aliasing`).
   - *(Item 2)* One Audio or Gameplay/General clarity setting they touched or inspected (e.g., `Improve Clarity` / `Boost Player Contrast`, `HRTF` / `EQ Profile`).
   - *(Item 3)* One setting they explicitly skipped, rejected, or locked (or a personal control they left untouched).
3. Score blindly (0–2 per dimension against catalogue ground truth):
   - **Function (0–2):** `0` = wrong/don't know; `1` = vague ("makes it faster/better"); `2` = accurate mechanism ("synchronizes rendered frames to monitor refresh to stop tearing").
   - **Trade-off / Consequence (0–2):** `0` = none/invented FPS gain; `1` = partial; `2` = accurate downside ("adds frame-buffer input delay when enabled; disabling can cause tearing").
   - **Justification (qualitative):** Did they cite a valid personal goal or only "the AI suggested it"?

### 4.2 Detecting & Mitigating Rubber-Stamping on Large Plans
Because comprehensive setups can stage 12–25+ items across categories, record these behavioral indicators per Condition B Task 2 trial:
* **Inspection depth:** Did they open **What I checked** or any **What it does & trade-offs** expander? Count of `Show in settings` jumps before Apply.
* **Modification / curation rate:** `(unchecked_count + edited_count + locked_count) / staged_count`. Zero edits paired with < 15 s total review across > 10 items signals likely rubber-stamping.
* **Process probe (think-aloud):** Right before the participant clicks **Apply selected changes**, ask neutrally: *"Before you apply those, pick any two changes in that list and tell me why you're keeping or skipping them."*

### 4.3 Local Model Latency & Fallback Contamination Rule
* **Warm-up before timing:** Before the participant begins Condition B, send one quick warmup turn while setting up (`ollama` keeps weights resident for `keep_alive="15m"`), then run **Study controls → Reset AI session only** so cold weight load (~10–20 s) does not skew Task 1.
* **Expected Mac (`arm64`, M4 24 GB) timing:** After prompt/batch optimization, expect ~`18.6–31.9 s` for narrow/explain/focused/follow-up turns, ~`74.5 s` for 12-item category plans, and ~`136.0 s` for full multi-category CS2 setup with `gemma4:12b-it-q4_K_M` (cold load adds ~6–20 s). Tell participants: *"The local assistant runs on this laptop rather than a cloud server, so full-menu reviews take a minute or two—nothing changes while it thinks."* Use a desktop GPU host if sub-10 s full-setup pacing is needed.
* **Strict Fallback Exclusion Rule:** Check the `Trace` tab after every session. If **any** Condition B turn fell back to deterministic rules (`source == "fallback"` / `Assistant offline — using basic suggestions`), flag that trial as `fallback_contaminated` in the study sheet and **exclude it from primary Local-AI condition averages** (report it cleanly in a separate reliability note).

---

## 5. Logging, Privacy & Per-Participant DB Isolation

* **Separate SQLite DB per participant:** Launch each session with a clean, isolated database file outside Git:
  `CSC2524_DB_PATH=data/local/pilot_P01.db .venv/bin/python scripts/dev.py`
* **Minimizing stored text (when needed):** If university ethics / course privacy prefers not retaining verbatim free-text utterances, set `STORE_CHAT_HISTORY=false` in `.env` (persisted traces retain only a 120-character goal excerpt rather than full message history).
* **Local-only exports:** Export session JSON via **Experimenter → Study controls → Export session JSON** at the end of *each* block into a local private study folder (e.g., `data/local/exports/`, never inside tracked Git folders). Reset demo state afterward with `.venv/bin/python scripts/reset_demo.py`.

---

## 6. Experimenter Checklist

- [ ] Verify Ollama is running and `.env` specifies `OLLAMA_MODEL=gemma4:12b-it-q4_K_M` (`smoke_check.py --real-model` OK).
- [ ] Launch with an isolated DB (`CSC2524_DB_PATH=data/local/pilot_PXX.db`).
- [ ] Send one throwaway prompt in Adaptive mode to warm `gemma4:12b-it-q4_K_M` weights, then click **Reset AI session only** + **Clear chat**.
- [ ] Check counterbalancing cell (G1–G4); run **Full reset** on `fresh_install_comprehensive`; set starting Condition (`A` or `B`) and starting Game (`VALORANT` or `CS2`).
- [ ] Toggle **Experimenter OFF** (`Participant` view) so condition pill, `Trace`, `Study controls`, and model tags are hidden.
- [ ] Brief participant: simulation-only disclaimer + think-aloud instruction.
- [ ] Administer Task 1 → Task 2 → Undo check → **Close Workspace/Chat & administer Blind Comprehension (3 items)** → Export Block 1 JSON.
- [ ] Switch to Block 2 (opposite Condition + opposite Game), run **Full reset** (`fresh_install_comprehensive`), toggle **Experimenter OFF**, repeat tasks + Blind Comprehension → Export Block 2 JSON.
- [ ] Optionally run Block 3 (`valorant_history_new_cs2` in CS2, Condition B `Discover` + `Pinned` + `?view=workspace`) → Export final JSON.
- [ ] Verify `Trace` tab for any unintended `fallback` turns and flag in observation sheet.

---

## 7. Realistic End-to-End Pilot Walkthrough Example

1. **Start in Participant mode (G1 / Condition B on CS2):** Participant sees `Counter-Strike 2`, `Simulated settings — no changes to VALORANT or CS2`, and docked chat.
2. **Narrow ask (Task 1):** Participant opens **Video → HUD Edge Positions**, pulls horizontal slider to `0.85`, sees live radar/health anchors shift inward, clicks **Done** (commits immediately without touching *Advanced Video* drafts).
3. **Comprehensive setup (Task 2):** Participant types *"I just installed CS2; configure everything for competitive FPS and clarity."* Chat shows live participant-safe progress (`Reviewing Video settings (1/2)…`) and responds concisely with **Review N changes** (`Changes` opens grouped by `Video`, `Audio`, `Game`; zero CS2 settings modified yet).
4. **Critical review & edit:** Participant expands **What it does & trade-offs** on `V-Sync`, unchecks one audio item they want left untouched, changes `MSAA` via inline dropdown to `4x MSAA`, clicks **Show in settings** on `Boost Player Contrast` to check its menu position, locks `V-Sync` from AI edits, and clicks **Apply selected changes**.
5. **Pinned direct edit + Undo:** Participant pins `EQ Profile`, opens **Pinned**, changes it directly (`Saved · Undo`), then opens **History** and clicks **Undo** on the applied batch to confirm clean rollback.
6. **Blind comprehension check:** Facilitator closes Workspace & Chat and asks *"Explain what V-Sync and MSAA control, and one trade-off of changing each"* — scoring `0–2` independently of chat text.
7. **Export & reset:** Facilitator toggles **Experimenter ON**, checks `Trace` (`source=ai`, zero fallbacks), exports `pilot_P01.json` locally, and runs `.venv/bin/python scripts/reset_demo.py`.

---

## 8. Blank Observation Sheet (Copy Per Participant)

```text
Participant ID: ______________   Date: ______________   Cell: [ ] G1 [ ] G2 [ ] G3 [ ] G4
Isolated DB Path: ______________________________   Warm-up done? Y/N
Trace Check: [ ] All B turns Local AI (`gemma4:12b-it-q4_K_M`)   [ ] Fallback occurred? (Turn #: ___ Tag: ai_fallback_contaminated)

BLOCK 1 — Condition: [ ] A [ ] B   Game: [ ] VAL [ ] CS2   Scenario: fresh_install_comprehensive
- Task 1 (Narrow/HUD or Crosshair):  Start: _____  End: _____  Search used? Y/N  Done/Explicit Apply clear? Y/N
- Task 2 (Comprehensive setup):      Start: _____  End: _____  # Final Changes Applied: ___  Unintended edits? ___
  (If B) Staged: ___  Category inspection? Y/N  Unchecked/Edited: ___  Show in settings clicks: ___
         What-I-checked / Trade-offs opened? Y/N  Think-aloud justification coherent? Y/N  Rubber-stamp flag? Y/N
- Undo Check completed cleanly? Y/N
- Blind Comprehension (Workspace & Chat CLOSED):
  1) High-impact Video setting (_______________): Function (0-2): ___  Trade-off (0-2): ___
  2) Audio/Clarity setting (___________________): Function (0-2): ___  Trade-off (0-2): ___
  3) Skipped/Locked/Unchanged (________________): Function (0-2): ___  Trade-off (0-2): ___  Agency reason: ____________
- Export filename (local only): ______________________________

BLOCK 2 — Condition: [ ] A [ ] B   Game: [ ] VAL [ ] CS2   Scenario: fresh_install_comprehensive
- Task 1: Start: _____  End: _____  Notes: __________________________________________________________________________
- Task 2: Start: _____  End: _____  Applied: ___  Staged/Unchecked/Edited (if B): _________________  Rubber-stamp? Y/N
- Undo Check completed cleanly? Y/N
- Blind Comprehension (Workspace & Chat CLOSED):
  1) High-impact Video setting (_______________): Function (0-2): ___  Trade-off (0-2): ___
  2) Audio/Clarity setting (___________________): Function (0-2): ___  Trade-off (0-2): ___
  3) Skipped/Locked/Unchanged (________________): Function (0-2): ___  Trade-off (0-2): ___  Agency reason: ____________
- Export filename (local only): ______________________________

OPTIONAL BLOCK 3 (Adaptive Transfer / Pinned / Detached View — Scenario: valorant_history_new_cs2)
- Used Discover Prepare for review? ___  Dismissed w/ reason? ___  Pinned direct edit? ___  Used ?view=workspace? ___

POST-SESSION RATINGS (1 = Strongly Disagree .. 7 = Strongly Agree) & DEBRIEF
- Condition A: Control: ___  Menu predictability: ___  Understood trade-offs: ___
- Condition B: Control: ___  Menu predictability: ___  Understood trade-offs: ___  Workspace clutter (1=low,7=high): ___
- Preferred Workspace placement: [ ] Docked  [ ] Detached (?view=workspace)  [ ] Depends
- Top friction / confusion / latency observation:
  _________________________________________________________________________________________________________________
```
