# Backend API (FastAPI, `http://127.0.0.1:8765`)

Interactive OpenAPI docs are served at `/docs` while the backend runs. Errors use one shape:
`{"error": "<code>", "message": "<human readable>", "details": {...}}` with 404 (unknown), 409 (conflict: stale
revision, locked, already applied/undone, run in progress, baseline condition) or 422 (invalid value/setting).

**Authority boundary:** no endpoint lets the assistant write values. Setting values change only through
`PUT /settings`, `POST /batch` (manual), `POST /proposals/{id}/apply` (explicit user approval) and history undo/reset.

## Meta and session
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness, version |
| GET | `/api/model/status?force=` | Ollama reachability, exact tag presence, details/capabilities, indicator (`connected` / `unavailable` / `fallback`) |
| GET / PUT | `/api/session` | `condition` (baseline/adaptive), `selectedGame`, `adaptationEnabled`, `aiMode` (local/fallback); switching never changes values |

## Catalogue, values, history
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/games` | Games with catalogue version and counts |
| GET | `/api/games/{game}/catalog` | Menu structure + flattened settings with provenance |
| GET | `/api/games/{game}/state` | Values `{id: {value, revision}}`, game revision, pins, locks, pending proposal ids, simulated hardware |
| GET | `/api/games/{game}/search?q=` | Settings matching text, with canonical location |
| PUT | `/api/games/{game}/settings/{settingId}` | Manual change `{value, expectedRevision?, clientRequestId?}` (optimistic concurrency, idempotent) |
| POST | `/api/games/{game}/batch` | Manual multi-change (CS2 *Apply Changes*, presets) — all-or-nothing |
| GET | `/api/games/{game}/history` | Change batches with before/after, source, proposal id, undoability |
| POST | `/api/history/{batchId}/undo` | Undo if nothing changed since (409 otherwise); recorded as a new batch |
| PUT | `/api/games/{game}/pins/{settingId}` · `/locks/{settingId}` | `{on: bool}` (adaptive condition only) |

## VALORANT Crosshair Profiles
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/valorant/crosshair/profiles` | List saved profiles (max 15) and active profile id |
| POST | `/api/valorant/crosshair/profiles` | `{name, copyFromCurrent}` — create/duplicate profile |
| POST | `/api/valorant/crosshair/profiles/import` | `{code, name}` — validate Riot `0;P;...;A;...;S;...` code & activate |
| POST | `/api/valorant/crosshair/profiles/{profileId}/select` | Switch active crosshair profile cleanly |
| PATCH | `/api/valorant/crosshair/profiles/{profileId}` | `{name}` — rename profile |
| DELETE | `/api/valorant/crosshair/profiles/{profileId}` | Delete non-last profile |
| GET | `/api/valorant/crosshair/profiles/{profileId}/export` | Serialize validated profile into Riot `0;P;...` code |

## Proposals (adaptive condition)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/games/{game}/proposals?status=` | Proposals with live staleness/lock/availability per item |
| POST | `/api/proposals` | Stage items `{game, source: ai/fallback/rules, runId, title, plan?, items:[{settingId, proposedValue, why, …}]}`; baseline value+revision captured server-side; locked/unavailable/no-op items stored as `blocked` |
| PATCH | `/api/proposals/{id}/items/{itemId}` | User edit of a staged value (validated) |
| POST | `/api/proposals/{id}/items/{itemId}/rebase` | User accepts that the setting changed since staging |
| POST | `/api/proposals/{id}/apply` | `{itemIds, idempotencyKey}` — revision + lock + domain re-check, all-or-nothing, 409 explains conflicts |
| POST | `/api/proposals/{id}/reject` | `{itemIds?, reason?}` — no value change; evidence recorded |

## Assistant (adaptive condition)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chat` | `{game, message, uiState, scopeOverride?}` → 202 `{runId, status:"running", steps}`; one run per game (409 if busy); validated recommendations auto-stage idempotently into `Changes` |
| GET | `/api/chat/runs/{runId}` | Progress steps while running; then `result` (validated response with `provenance`), tool calls, validation report |
| POST | `/api/chat/runs/{runId}/cancel` | Cancel; nothing is changed |
| GET / DELETE | `/api/games/{game}/chat` | Thread for the current session / clear it |
| GET | `/api/traces?game=&limit=` | Concise run traces (run id, condition, game, ≤120-char goal excerpt, model, tools, validation, latency, outcome) |

## Relevant now, context, profile
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/games/{game}/relevant-now` | Held card set (first visit computes it), `updateAvailable` flag, live card states |
| POST | `/api/games/{game}/relevant-now/refresh` | User-confirmed refresh |
| POST | `/api/games/{game}/relevant-now/dismiss` | `{settingId, reason}`; suppressed until the evidence signature changes |
| GET / POST | `/api/context-events` | Simulated event types / set one `{game, eventType|null}` (refreshes Relevant now) |
| GET | `/api/profile` | Durable + session preferences with evidence, session goals, context, recent evidence |
| POST / DELETE | `/api/profile/preferences[/{id}]` | Explicit user preference (`source`: `user_explicit` or `chat_confirmed` only) |
| DELETE | `/api/games/{game}/session-goals` | Clear the transient goal |

## Study administration
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/scenarios` | Synthetic scenarios |
| POST | `/api/admin/reset` | `{scenario, mode: full/ai_only}`; writes a JSON backup first |
| GET | `/api/admin/export` | Full state as JSON |
| POST | `/api/admin/import` | Restore an export (backs up the current state first) |
