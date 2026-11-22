# Adaptive Settings Agent

Adaptive Settings Agent is a CSC2524 HCI research prototype for exploring whether conversational guidance can make complex settings easier to find, understand and change while keeping the menu familiar. VALORANT and Counter-Strike 2 (CS2) serve as examples of settings interfaces with many controls, dependencies and trade-offs.

- **Baseline (A)** provides both games’ canonical navigation (`315` verified/labelled settings: `177` VALORANT incl. 15-profile Crosshair editor & live SVG preview + `138` CS2 incl. HUD Edge Positions safezone preview & `New` tab), search, manual controls and change history with undo.
- **Adaptive (B)** keeps the same catalogues, row order and manual controls. It defaults to a clutter-free **Participant view** (hiding condition pills, scenario resets, model IDs and raw traces behind an **Experimenter** toggle) and unifies **Changes** (idempotently auto-staged from chat without auto-applying), **Pinned** (direct manual controls that respect user authority even over AI locks), and **Discover** (proactive/cross-game cards) inside a docked or detachable (`/?view=workspace`) **Adaptive Workspace**.
- **Preferences** distinguish temporary goals from confirmed durable preferences. Cross-game recommendations can use priorities such as visibility or input latency while leaving each game’s values independent.

The project is an unofficial simulation and has no affiliation with Riot Games or Valve. Settings changes apply only to the prototype’s SQLite database. Hardware and context events are simulated, the prototype measures no in-game performance, and no human-participant study has been conducted. Some catalogue entries have partially verified paths, bounds, or defaults. The catalogue records those distinctions.

## Architecture

React, TypeScript and Zustand render the two game menus. Vite proxies browser requests to FastAPI during development. The backend loads versioned JSON catalogues and synthetic scenarios, and SQLite stores values, preferences, history, and proposal state. FastAPI can also serve the production bundle on one port.

LangGraph orchestrates the assistant and uses LangChain’s `ChatOllama` integration for local inference. An intent-scope classifier (`explain_only`, `focused`, `category_optimization`, `broad_optimization`, `full_game_setup`) and deterministic coverage planner let the workflow skip redundant planning rounds when grounded (`AGENT_FAST_PATH=true`) or call read-only lookup tools, compose schema-constrained recommendations (with category-packed batching for comprehensive setups), and fall back to labelled rules when Ollama is unavailable. Backend validation checks proposed IDs, values, dependencies and locks, auto-stages validated changes idempotently for user review, and rechecks them atomically when the user confirms Apply. See the [API reference](docs/API.md), [catalogue report](docs/CATALOG_REPORT.md), [completeness audit](docs/SETTINGS_COMPLETENESS_AUDIT.md), [requirements matrix](docs/REQUIREMENTS_MATRIX.md), [design audit](docs/NEXT_PASS_DESIGN_AUDIT.md), [research rationale](docs/RESEARCH_RATIONALE.md), [pilot protocol](docs/PARTICIPANT_PILOT.md), and [research notes](docs/PAPER_IMPLEMENTATION_NOTES.md).

## Prerequisites

- Git, Python **3.11**, and Node.js **24 LTS** with npm. Node 22.12 or later in the 22.x line also satisfies the frontend’s declared requirements. CI uses Node 24.
- For live inference, install [Ollama](https://ollama.com/download) and start its desktop app or run `ollama serve` in another terminal. Fallback mode works with an empty `OLLAMA_MODEL`.
- Ollama requires macOS 14 Sonoma or newer. The [Ollama macOS guide](https://docs.ollama.com/macos) lists GPU and CPU support for Apple Silicon and CPU-only support for Intel. The verified model has about 8 GB of weights, and inference requires additional memory for context and overhead. Expect slower inference on CPU-only hardware.

### macOS

```bash
git clone https://github.com/SpaceJesusTM/adaptive-settings-agent.git
cd adaptive-settings-agent
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
cp .env.example .env
```

For live inference, start Ollama and run `ollama list`. If you want the Windows project’s verified model and it is missing, run `ollama pull gemma4:12b-it-q4_K_M` manually, then set `OLLAMA_MODEL=gemma4:12b-it-q4_K_M` in `.env`. Use the exact tag from `ollama list` for any other model.

```bash
python scripts/dev.py --reload
```

Open [the development app](http://127.0.0.1:5173/), or run `open http://127.0.0.1:5173/` from a separate terminal.

### Windows 11 (PowerShell)

```powershell
git clone https://github.com/SpaceJesusTM/adaptive-settings-agent.git
Set-Location adaptive-settings-agent
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
Copy-Item .env.example .env
```

For live inference, use `ollama list` and edit `.env` with the model tag as described above.

```powershell
python scripts/dev.py --reload
```

Open [the development app](http://127.0.0.1:5173/). If PowerShell blocks activation, replace `python` in the installation and launch commands with `.\.venv\Scripts\python.exe`. If an older bundled pip reports a Windows certificate verification error while upgrading, try `python -m pip --use-feature=truststore install --upgrade pip` to use the Windows certificate store.

## Local model and data

| Setting | Purpose |
| --- | --- |
| `OLLAMA_BASE_URL` | Defaults to `http://127.0.0.1:11434`. |
| `OLLAMA_MODEL` | Exact installed tag. An empty value selects the offline fallback. |
| `OLLAMA_TIMEOUT` | Per-request timeout in seconds, default 90. Existing configurations can still use `OLLAMA_TIMEOUT_S`. |
| `AGENT_DEADLINE_S` | Overall assistant turn deadline, default 150 seconds. |
| `BACKEND_PORT` / `FRONTEND_PORT` | Default to 8765 and 5173. Set these in the root `.env` before starting the app. |
| `CSC2524_DB_PATH` | Defaults to `data/local/app.db`. Relative paths are anchored at the project root. |

The original Windows installation uses `gemma4:12b-it-q4_K_M` (Gemma 4 12B instruct, Q4_K_M). The app uses the configured tag and does not initiate model downloads. See [local model setup and troubleshooting](docs/MODEL_SETUP.md).

SQLite initializes on first startup. Study controls let you switch conditions, load synthetic scenarios, simulate context events or explicitly select the offline fallback. Reset writes a JSON backup beside the database in `backups/`. Treat exports, backups and diagnostic traces as private. Git syncs project code and the synthetic fixtures between machines. Each checkout keeps its own `.env`, database, and Ollama installation.

The development servers bind to loopback by default. Keep them local. The prototype has no user authentication, and its study controls can reset or export state.

## Development and tests

```text
python -m pytest -c backend/pytest.ini
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run e2e
```

The build includes TypeScript checks. Browser journeys use a dedicated test database and offline rules. For browser journeys, Windows uses Edge by default. On macOS install Chromium once with `npm --prefix frontend exec -- playwright install chromium`, or run against system Chrome with `PW_CHANNEL=chrome npm --prefix frontend run e2e`. CI uses Chromium on Windows and macOS and requires no Ollama service or repository secrets.

Use `python scripts/dev.py --backend` and `python scripts/dev.py --frontend` in separate terminals when you want independent logs. Use `python scripts/dev.py --serve` for the built application at port 8765. When a port is busy, change it in `.env` and restart both processes. Use `python scripts/smoke_check.py --backend --real-model` while the backend and Ollama are running to check the configured live model.

For daily development, commit and push from either checkout and use `git pull --ff-only` from a clean checkout on the other machine. Install again from the lockfiles after dependency changes. The backend’s `requirements.txt` installs the pinned runtime subset, and `requirements-dev.txt` adds pytest.

## Credits and license

VALORANT and Counter-Strike 2 setting references are credited in the [catalogue audit](docs/GAME_SETTINGS_AUDIT.md). Barlow and Barlow Semi Condensed are by Jeremy Tribby and contributors. Saira Semi Condensed is by Omnibus-Type and contributors. Fontsource distributes these fonts under the SIL Open Font License 1.1. Their license texts are included in the respective npm packages.

The project has no project-wide license. Public visibility permits viewing and forking on GitHub under its terms. Copyright otherwise governs reuse and redistribution. Third-party dependencies retain their own licenses. See [GitHub’s licensing guide](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).
