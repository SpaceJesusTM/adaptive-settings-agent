# Decision log

Newest last. Each entry: decision, reason, consequence.

### D-01 — Local model: `gemma4:12b-it-q4_K_M` (user-approved, 2026-11-21)
* **Observed:** the user's stated model "Gemma 14B Q4" was **not installed**. `ollama list` (Ollama 0.40.17, store `E:\OllamaModels`) showed only `qwen2.5-coder:7b`, `qwen2.5-coder:14b`, `qwen3.5:9b`. The official Ollama `gemma4` library has no 14B tag (e2b, e4b, 12b, 26b-a4b, 31b).
* **Decision:** asked the user; the user explicitly chose to pull **`gemma4:12b-it-q4_K_M`** (official Gemma 4 12B instruct, Q4_K_M). Pulled 2026-11-21; `ollama show` reports architecture `gemma4`, **11.9B** parameters, quantization `Q4_K_M`, ID `6114515d63c1`.
* **Consequence:** documentation never calls it "14B". The model is configured only through `OLLAMA_MODEL`; no other model is silently substituted. Evidence in `MODEL_SETUP.md`.

### D-02 — Structured JSON at the final boundary, native tool calls for read tools
* **Observed (probe, 2026-11-21):** the model returns schema-valid JSON with Ollama `format` (JSON schema) with `think` on or off, and emits native `tool_calls` for a declared function.
* **Decision:** LangGraph workflow = deterministic context retrieval → bounded native tool-calling loop over **read-only** tools → one schema-constrained JSON call for the final answer → deterministic server-side validation. If native tool calls fail, the workflow continues with pre-retrieved context only (still schema-validated).

### D-03 — Stack
FastAPI + Pydantic v2, stdlib `sqlite3` with a versioned schema bootstrap (no ORM), LangGraph + `langchain-ollama`; React + TypeScript + Vite, Zustand for client state, Vitest + Testing Library, Playwright (system Edge/Chrome channel when bundled browsers are unavailable). Minimum Python **3.11**, Node.js **20.19+ / 22 LTS / 24 LTS**.

### D-04 — Locks guard against AI, not against the user
A lock (`Locked from AI`) prevents the setting from being included in AI or rule-based proposals and from being applied through any proposal. Manual edits and user-initiated undo are still allowed (the user is the authority). This keeps the baseline condition identical (locks are invisible there) and is stated in the UI.

### D-05 — Function vs. rationale explanations come from different sources
"What it does" and trade-offs are rendered from the **verified catalogue** (source-linked). "Why this may help your goal" is the **model's rationale** (or a rule template in fallback mode) and is labelled with its origin. This keeps DG2's two explanation types distinct and prevents the model from inventing setting semantics.

### D-06 — Relevant Now is deterministic and held
Proactive cards are ranked by a transparent rule (preference/goal dimensions × catalogue goal hints, excluding locked/dismissed/already-satisfied settings). The visible set only changes on an explicit trigger (first game visit, simulated context event, user refresh, preference change) and never while a card is expanded or being edited; otherwise a "New suggestions available" notice is shown.

### D-07 — Search is a prototype-level feature in both conditions
Neither game is assumed to have settings search. The prototype offers the same search in both conditions (condition parity); results navigate to the canonical row instead of showing copies.

### D-08 — Chat runs are asynchronous and single-flight
`POST /api/chat` starts a run and returns a `run_id`; the UI polls run status (progress steps, cancel). One active run per game/session; a second request receives 409 instead of interleaving proposals.

### D-09 — CS2 data from the game's own files; VALORANT from Riot documents and screenshots
CS2 labels, options, slider ranges, tooltips, defaults, presets and default keys were extracted from the CS2 client
files of build 2000948 (2026-11-20) as mirrored by SteamDatabase GameTracking-CS2 (pinned commit 694f81f). Nothing is
copied into the project except the factual strings needed for the simulation. VALORANT has no equivalent public
source, so Riot support articles (incl. embedded menu screenshots) and the official 2025-2026 patch notes are used,
with dated third-party guides only as flagged secondary evidence.

### D-10 — VALORANT Crosshair tab shown but not simulated
No current Riot source documents the crosshair editor's exact labels and ranges after the 2026 updates. The tab and
its sub-tabs stay in the navigation (recognisable menu) but render a labelled "not simulated" page rather than
invented controls. Same for VALORANT Stats/Voice-Over and three Controls sub-tabs, and CS2 "New"/"HUD Edge Positions".

### D-11 — Post-12.07 VALORANT section placement is inferred and marked
Patch 12.07 split *General > Other* into *User Interface / Content Filtering / Network* without listing the moved
settings. The 17 affected settings are placed by topic, flagged `pathVerification: inferred`, and marked ⓘ in the menu.

### D-12 — CS2 Video keeps its native explicit Apply
CS2 applies video changes with *Apply Changes / Discard Changes*; the simulation keeps this (`applyMode: explicit`),
including the video preset that expands to its eleven member settings. AI proposals are applied through the review tray
instead; a tray apply is refused while conflicting unapplied video edits exist.

### D-13 — Prompt iteration with the real model (2026-11-21)
The first real-model run (`docs/evidence/model_runs/20261121-101359/`) showed Gemma asking clarifying questions even
for clear goals. The compose prompt now contains an explicit intent decision procedure (clarify only when no goal is
named; trade-offs go into `tradeoff_note`). The planning call is capped at 160 output tokens so it cannot draft a full
answer. Both changes are recorded with before/after evidence.

### D-14 — "Based on …" is grounded by the server
When a recommendation's goal dimension matches a stored session goal, saved preference or simulated context event,
the validator fills `basedOn` from those records (e.g. "your saved preference for low input latency in VALORANT")
instead of trusting model text. Cross-game provenance is therefore shown reliably.

### D-15 — Sensitivity and keybinds are never AI-proposable
Mouse sensitivity scales differ between games and are personal; keybinds are personal. They are explicable but never
proposable, which also guarantees that cross-game transfer cannot copy a numeric sensitivity.

### D-16 — E2E isolation
Playwright starts its own backend (port 8766, `data/local/e2e.db`) and Vite (5174) and uses the installed Edge on
Windows, so automated tests never touch the user's demo database and need no browser download.
