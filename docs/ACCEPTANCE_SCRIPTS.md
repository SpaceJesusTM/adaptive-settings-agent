# Manual acceptance scripts

Start from **Experimenter -> Study controls -> Full reset** of the named scenario, then toggle **Experimenter OFF** when testing clean participant UX. “Pass” criteria are observable in the UI; most are covered by automated tests.

## 1. Find an unfamiliar setting & Participant presentation (both conditions)
* Scenario `default`, condition A. Verify neither A/B pills, *Study controls*, *Trace*, nor model IDs appear in Participant mode.
* Use tabs or search (*minimap*) -> jumps to *General > Map > Minimap Zoom* in place and highlights it; no rows moved. [E2E: *search takes the user to the canonical row*, *participant default hides A/B switcher...*]

## 2. Understand an explanation (condition B)
* Ask *“What does anti-aliasing do?”*.
* **Pass:** *explain_only* stays compact with *What it does* (catalogue source) separate from *Why this may help*; *Show in settings* highlights *Video > Graphics Quality > Anti-Aliasing*. **Nothing is staged in Changes or changed.**

## 3. Auto-staged goal plan & comprehensive fresh-install setup (condition B)
* Scenario `fresh_install_comprehensive` (or `default`). Ask *“I just installed CS2; configure everything for competitive FPS and clarity.”* (or a focused perf ask in VALORANT).
* **Pass:** assistant answer is compact with provenance pill, collapsed *What I checked*, and **Review N changes** button; active game values remain unchanged before Apply. Clicking **Review N changes** opens **Workspace -> Changes** grouped by category. Edit one value -> **Apply selected changes** -> *History* records *AI proposed · user applied* (or *Fallback suggestion · user applied*); *Undo* restores everything. [pytest: `test_comprehensive_setup.py`; E2E: *comprehensive fresh-install setup...*]

## 4. Well-configured competitive check (no forced churn)
* Scenario `well_configured_competitive`. Ask to optimize competitive settings.
* **Pass:** zero unnecessary recommendations forced (`Changes` stays empty) because relevant controls are already configured cleanly. [pytest: `test_well_configured_scenario_has_zero_forced_changes`]

## 5. Pinned direct edits, AI locks & CS2 Video pending-draft guard
* Pin *VSync*, lock it from AI (`🔒 AI locked`), open **Workspace -> Pinned**, and toggle VSync directly via its inline `SettingControl`.
* **Pass:** saves immediately (`Saved · Undo`), **zero** proposals created, and AI proposals referencing locked settings still block them (`blocked`). In CS2, make an unapplied *Advanced Video* edit, then adjust a pinned explicit-apply Video setting -> UI asks whether to apply pending Video drafts or save only the single edit instead of silently losing drafts. [vitest + E2E]

## 6. Discover (`Prepare for review`), cross-game transfer & dismissal
* Scenario `valorant_history_new_cs2` in CS2 -> **Workspace -> Discover**.
* **Pass:** CS2 suggestions cite VALORANT abstract preferences, exclude numeric *Mouse Sensitivity* and VALORANT IDs, hold across reload, move to *Changes* only after clicking **Prepare for review**, and do not reappear once dismissed with a reason.

## 7. Detachable workspace sync, VALORANT Crosshair & CS2 HUD Edge Positions
* Open `/?view=workspace&game=valorant` in a second tab/window; trigger changes -> both tabs synchronize automatically.
* Switch to **VALORANT -> Crosshair -> Primary**: create/select/import `0;P;c;5;h;0;0l;4;0o;2;0a;1;0f;0;1b;0` and verify live `<ValorantCrosshairPreview>` SVG updates & persists on reload.
* Switch to **CS2 -> Video -> HUD Edge Positions** after leaving an unapplied *Advanced Video* draft: adjust Horizontal/Vertical sliders -> live safezone preview moves; click **Done** -> `hud_edge_x`/`y` save immediately while the unapplied Video draft stays pending. Verify **New** tab links cleanly to promoted settings.

## 8. Condition parity, Study controls & failure paths
* Enable **Experimenter** -> verify A/B switcher produces identical canonical menu rows and order; stop Ollama or select *Offline fallback* -> fallback answers remain explicitly labelled and cancel leaves state clean.
