# Integration recommendations

GamePlan is strongest when it keeps the canonical menu intact and treats the assistant as a collaborator at review time. It already supports explicit Apply, targeted manual control, locks, editable drafts, history and recovery. The audit found several failures upstream of that authority boundary. Intent could be classified as a different optimization goal, a valid setting could violate an explicit exclusion, a scoped preference could overwrite another game's preference, and a literal change could trigger broad optimization. In those cases an accurate settings catalogue still produced poor assistance.

## Decisions

| Change and goals | Evidence and alternatives | Recommendation |
| --- | --- | --- |
| **Shared current objective and exclusions**, DG2–DG4. `objective.py`, `validate.py`, `planner.py`, `profile.py`, `proposals.py`. | MAESTRO grounds decisions in shared feasibility and preference records. Just-In-Time Objectives isolates the immediate task. Held-out VSync and shadow requests and the B2 protected categories had violations in the baseline and zero in candidate replay. The current resolver has bounded phrase and setting-name coverage. | **Integrate now.** Treat recognized exclusions as eligibility checks. Keep full canonical access and a visible outdated-draft warning. Leave unrestricted natural-language constraints for evaluation. |
| **Scoped preferences and grounded corrections**, DG3–DG4. `profile.py`, migration 5, `runner.py`, System Understanding. | The two opposite, game-scoped preferences coexist and targeted withdrawal preserves the other game. The temporary goal does not erase the durable priority. The existing structured layout plus a shared objective is a lower-cost comparison to free-form extraction on every turn. | **Integrate now.** Maintain separate source, scope and status. Use structured preference confirmations for ambiguous wording. |
| **Catalogue-backed exact requests and recovery**, DG2–DG3. `exact.py`, `runner.py`, Chat. | The separately scored fixtures exercise eight exact targets and two historical restores. Manual-only controls receive location and values. Staged settings still use normal validation, review and Apply. Cocoa motivates explicit editable review. The bounded parser does not resolve every multilingual or historical reference. | **Integrate now.** Keep literal-value rules and the normal fallback for other requests. |
| **Discover stability and evidence-sensitive onboarding**, DG1–DG4. `recommender.py`. | ReLay and Todi motivate reversible, low-cost intervention. Manual onboarding already worked and remains useful. Card identities survive unrelated edits, scoped dismissals prevent recurrence, and Undo does not count as a new deliberate choice. | **Integrate stability and provenance.** An inspect-only aligned card closes a measured objective-switch gap. Pilot its timing and relevance before treating it as a demonstrated discovery benefit. |
| **Fidelity coverage and compact comparisons**, DG1–DG2. `valorant.json`, `explain.py`. | A2 has independently scored goal coverage. Missing hints were added from setting function and labeled editorial. The explanation comparisons cover hardware refresh versus frame rate and CS2 shadow options. Buçinca et al. provide a hypothesis for independent learning. | **Integrate the grounded facts.** Further test educational depth and user learning, including when extra information is helpful. |
| **Alternative adaptive policies and memory infrastructure**, DG1–DG4. | LangMem, Mem0 and MAESTRO show more general extraction and planning approaches. PrefEval suggests benchmark extensions. A general vector memory and LLM reranking add cost, and this audit did not establish benefit over scoped SQLite and deterministic policy. | **Defer.** Reject silent copying of personal settings, adaptive hiding or reordering of the canonical settings menu, and automatic promotion of accepted advice to lasting preference. |

## Where model reasoning earns its cost

Use the local model for open objectives, ambiguous language, comparisons requiring composition and useful trade-off explanations. Preserve deterministic parsing of exact commands, numeric conversion, catalogue eligibility, hardware checks, explicit exclusions, profile writes and history. The broad planner's audited candidates and compact facts give the model grounding, while local runs still require per-case coverage and latency checks. The [evaluation](EVALUATION_RESULTS.md) distinguishes model output, deterministic rules and fallback.

System Understanding should show the effective current objective, protected settings, scoped confirmed priorities, direct actions and their provenance, and correction controls. The player should be able to infer why a suggestion appeared from the place it was offered. Discover should surface worthwhile unfamiliar or overlooked controls and explicit cross-game onboarding opportunities. It can stay quiet when context adds little.

## Integration and rollback

Review the commits below in dependency order. Keep the release or presentation build separate until the intended branch is chosen explicitly. Keep the target database isolated when rehearsing the audit test fixtures.

1. `1f19069` shared objectives, scope, validation, literal requests and explanations.
2. `561bd8c` Discover policy and regression tests.
3. `2f9a09d` fidelity catalogue hints.
4. `d4dcb3e` reproducible behavioral benchmark.
5. `274fcd6` validation diagnostics contract.
6. `6120233` whole-word dimension matching and equivalent concept scoring.
7. `f82ce26`, `aa88f29` explicit crosshair note and bounded correction follow-up.
8. `4de6c69` publish detached game selection before background refresh.
9. `85f106e` add the independent held-out probes.

For a complete comparison, keep `c75d81e2e726fd14e26a3f31e6961f925cb097f4` and the experiment in different checkouts with separate data. The database migration adds nullable preference applicability and a default empty protection list. Existing preferences and objectives read normally on the candidate. For rollback, use the earlier checkout with its own database. An older build cannot interpret the newly scoped preference semantics if pointed at a candidate database.

## Presentation evidence

Show that GamePlan can preserve a complete settings menu while providing explainable, reviewable help that changes with a player's goal. Demonstrate scope, exclusions and recovery with the [walkthroughs](DEMO_IMPROVEMENTS.md). Report the paired simulator scores and exact-setting outcomes with model or rule provenance. A comprehension study is required to establish learning, and real game tests would be required to establish FPS, latency or image-quality effects.
