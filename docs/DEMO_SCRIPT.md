# Demo script (about 7 minutes) and backup plan

## Before the demo (2 minutes)
1. Start Ollama (`ollama serve` or Ollama desktop app).
2. `.venv/bin/python scripts/smoke_check.py --real-model` — expect `Configured model installed` (`gemma4:12b-it-q4_K_M`) and a passing structured request.
3. `.venv/bin/python scripts/reset_demo.py` (backs up, then restores the *default* synthetic scenario).
4. `.venv/bin/python scripts/dev.py` and open `http://127.0.0.1:5173/` at `1440×900` (or `1280×720` / detached `?view=workspace`).
5. Warm `gemma4:12b-it-q4_K_M` once in Adaptive mode (`Experimenter -> Study controls -> Reset AI session only` afterward). Leave **Experimenter** toggled OFF for participant view.

## Script
1. **Two authentic menus, Participant chrome (40 s).** Point at the *Simulated settings — no changes to VALORANT or CS2* pill (notice zero study clutter, no raw model tag). Browse **VALORANT → Crosshair → Primary** (live SVG crosshair + import/profiles), then switch to **CS2 → Video → HUD Edge Positions** (live safezone preview saving via **Done** separately from Video *Apply Changes*) and **CS2 → New**.
2. **Baseline (40 s).** Toggle **Experimenter** briefly to show identical menu rows between **A · Static baseline** and **B · Adaptive**. In A: search “anti-aliasing” → highlights canonical row; toggle *Bloom* Off → toast → **History** → *Undo*.
3. **Auto-staged comprehensive plan (90 s).** Reset to `fresh_install_comprehensive` in Condition B (Participant view). Ask: *“I just installed CS2; configure everything for competitive FPS and clarity.”* Point at the compact answer (provenance pill, collapsed *What I checked*, **Review N changes** button) — active CS2 values are still untouched. Click **Review N changes** to open **Workspace → Changes** grouped by category; inspect *What it does & trade-offs*, edit one value, lock *VSync*, apply selected, and demonstrate **Undo**.
4. **Pinned direct controls & detachable sync (60 s).** Pin a setting (even when AI-locked), open **Workspace → Pinned**, adjust its inline control directly (*Saved · Undo*, zero proposal overhead), and pop out **Open in new window** (`?view=workspace`) to show real-time cross-window sync.
5. **Cross-game transfer & Discover (60 s).** Open `valorant_history_new_cs2` in CS2 → **Workspace → Discover**: cards explain *Based on … in VALORANT*, exclude sensitivity/keybinds, and only stage into *Changes* on **Prepare for review**.
6. **Experimenter diagnostics & safety (40 s).** Toggle **Experimenter** ON -> ask a prompt-injection in `locked_settings` and inspect **Trace** showing validator filtering and tool calls.

## Backup procedure (model unavailable or slow)
* **Experimenter -> Study controls -> Assistant source -> Offline fallback.** Every answer is labelled *Offline fallback — rule-based, not AI-generated*; the full auto-stage / Workspace / Crosshair / HUD Edge / cross-game flow remains runnable.
* Use `.venv/bin/python scripts/dev.py --serve` for single-port serving on 8765. Pre-generate offline figures via `PW_CHANNEL=chrome npm --prefix frontend run screenshots`.
