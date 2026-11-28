# GamePlan research audit progress

## Baseline and isolation

Started November 28, 2026. The audit branch was created in a sibling worktree from the local and remote `feat/comprehensive-ux-settings-pass` HEAD `c75d81e2e726fd14e26a3f31e6961f925cb097f4`, 15 commits past `main` (`ff6874eacbac720444f86ba22ec0b050c53ba937`). The original working tree was clean. The audit uses its own ignored configuration, SQLite files, runtime logs and ports 18765–18766. Live evaluation uses a new temporary database for every case. The existing Ollama tag is `gemma4:12b-it-q4_K_M`; no models were downloaded.

Read the current Presentation Outline, Paper Outline, Pass 1 and follow-up requirements, and Pilot Tasks and Measures in the project document. Private text stays outside Git. The actual pilot's A/B task families take precedence over older examples in the repository protocol. Research assistants are independently reading primary literature and source implementations outside the worktree. The lead is implementing and reviewing the changes.

## Hypotheses recorded before experiments

1. Using a common request interpretation for the planner, validator, persisted current objective and Discover should preserve explicit exclusions and keep temporary objectives from competing on equal terms with older preferences. Preserve the present SQLite distinctions between objectives, confirmed preferences and observations. Compare excluded changes, objective contamination, scope and recovery against the pinned baseline.
2. Keep deterministic Discover generation, but retain cards when the candidate and its evidence are unchanged, suppress the same dismissed goal suggestion despite unrelated evidence, and keep clean onboarding available. Compare card identities, dismissal recurrence and traceable cross-game checks. An empty view is valid.
3. A bounded catalogue-backed path for explicit setting/value requests and targeted recovery should improve exactness and save inference. The same staging and validation boundary applies. For mixed optimization/explanation turns, retain the bounded model path and check whether deterministic grounding improves coverage.
4. Treat optional educational content and broader LLM reranking as separate hypotheses. A favourable automated result would establish only technical behaviour in the simulation.

## Checks in progress

Baseline backend 116/116, frontend 28/28 and build passed. The default Playwright executable revision was absent. The baseline browser run was restarted with installed Chrome. The original live-model suite is running. Pending work includes same-case comparisons, real-model walkthroughs, integration decisions and final invariant checks.

## Experimental implementation and verification

- `1f19069` grounded current objectives, scoped memory, setting exclusions and explicit catalogue/history turns.
- `561bd8c` preserved Discover card identity, improved dismissal and source checks, and added an aligned inspection experiment.
- `2f9a09d` added editorial fidelity hints for UI quality, anisotropic filtering and cast shadows.
- `d4dcb3e` introduced the behavioral runner. `274fcd6` retained the validation diagnostic contract. `6120233` disambiguated dimensions with word boundaries and accepted an equivalent wording for the VSync concept scorer.
- `f82ce26` and `aa88f29` added a bounded crosshair memory note and separated corrections from setup prompts. `4de6c69` fixed an intermittent detached-window selection race found in Playwright. `85f106e` added 13 additional probe fixtures.

The original suite finished with 116 backend checks, 28 frontend checks, a successful build, 25 Chrome browser journeys, and 15 Gemma answers plus one intentionally unavailable-endpoint fallback. The experimental backend finished 120 checks. The focus-window browser fix passed three repeated runs. The first common API matrix measured 52/83 baseline and 82/83 candidate on each of three candidate repetitions. The expanded matrix measured 58/100 and 97/100 on 42 fresh-state scenarios and 57 turns per revision. Remaining misses are B2 full credit, literal value plus a time phrase, and voice-modality memory. The aligned Discover ablation failed precisely the objective-switch Discover assertion.

The baseline live suite ran before paired live inference. The final browser rerun and paired comparison are recorded below.


## Completion

The final full Chrome suite passed 25/25, frontend tests passed 28/28, build passed, and the HTTP smoke run passed eight checks. A scratch version-4 database migrated to version 5 and retained its legacy preference and session objective. The six existing deterministic scenario replays completed. An additive-objective ablation showed one stale performance diagnostic in the temporary fidelity plan despite otherwise identical check totals.

The paired local subset completed nine scenario groups and 12 turns per revision using the existing Gemma tag. Baseline passed 26/35 assertions with one deadline fallback. Candidate passed 33/35 with one deadline fallback and two deterministic rules turns. Both had zero chat-time committed setting changes. Candidate Gemma completed A2 at 8/8 and B2 at 7/8 with no protected changes. Both broad pilot turns remained slow. The expanded deterministic benchmark passed 97/100 against baseline 58/100, with three named limitations in the evaluation.

All ten reports and sanitized evidence were prepared for local review. The experimental implementation evaluated at `85f106ea3a4d706d4bc6abe3edb1705748b72831` is followed by an evidence-only commit. Both original branch tips remained at their recorded SHAs, and the original checkout remained clean. The detached baseline scratch worktree was removed. The audit branch remains local with independent runtime data.
