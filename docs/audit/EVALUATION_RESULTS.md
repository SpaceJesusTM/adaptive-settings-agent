# Experimental evaluation

The comparison uses the comprehensive UX baseline at `c75d81e2e726fd14e26a3f31e6961f925cb097f4` and the audit implementation. State is synthetic and isolated per case. These runs measure simulator behavior, not human outcomes or in-game performance.

## Methods and repeatability

The [behavioral runner](../../scripts/run_audit_benchmark.py) calls the real FastAPI route layer with isolated temporary SQLite and the normal services. It records controlled start values, assistant outputs, staged items, Discover evidence and actual post-action state. Project cases cover the standardized goal, exact and recovery tasks. Development cases reproduce known routes. Held-out cases use separate phrasings or histories and independently score selected aspects. Runtime catalogue files and prompts never load the benchmark. The candidate added editorial hints from documented control behavior. A2's eight-point scorer and eligibility checks are in the harness and outside runtime context.

For A2 and B2, the standardized policy explicitly applies all staged items once. It records true committed values and separate proposal, protected-control and aligned-setting checks. Many out-of-rubric changes can be reasonable. These are reported individually for inspection, not automatically counted as incorrect. The authority journey uses a different controlled policy, including editing, rejecting, locking, undoing and restaging. The exact journey separately scores guidance when a manual setting can't be staged and records the subsequent manual fixture action. The explanation score checks concepts and catalogue targets. Spot review reads actual text and separately considers trade-offs and uncertainty. There is no model judge.

```bash
git worktree add --detach ../gameplan-audit-baseline c75d81e2e726fd14e26a3f31e6961f925cb097f4
python scripts/run_audit_benchmark.py --repo ../gameplan-audit-baseline --out /tmp/gameplan-baseline.json
python scripts/run_audit_benchmark.py --repo . --out /tmp/gameplan-candidate.json
```

For paired local inference, set `OLLAMA_MODEL` to `gemma4:12b-it-q4_K_M`, keep the Ollama service running, and add `--mode local --cases a2 b2 mixed_request a1_b1_onboarding b_objective_shift c_review_recovery combined_exact_request explain_ao explain_fps_hz` to each invocation. This runner ignores checkout `.env` and accepts explicitly provided model configuration. Run model suites sequentially on the same machine. Each completed case checkpoints its JSON and per-case results include the source and recorded usage.

## Regression and environment

| Check | UX baseline | Experimental implementation |
| --- | --- | --- |
| Backend pytest | 116 passed | 120 passed |
| Frontend unit | 28 passed | 28 passed |
| TypeScript and production build | Passed | Passed |
| Playwright | 25 passed using installed Chrome | 25 passed after the synchronization fix |
| Local stock evaluation | 15 Gemma answers and one deliberately unavailable-model fallback | Paired subset below |

The HTTP smoke check passed all eight checks, the six existing scenario replays completed, and an isolated v4→v5 SQLite migration preserved legacy global applicability and its session objective. The test suite's default Chromium revision was absent, so both checkouts used the same installed Chrome channel. An additional candidate run intermittently missed game-selection sync when a detached window reloaded after its URL changed. The committed selection was published only after ancillary requests that could be cancelled by reload. `4de6c69` publishes once the server accepts the game change, and the focused browser journey passed all three reruns.

Machine and runtime as observed on November 28, 2026 were Apple M4 with 24 GiB unified memory and 10 CPU cores, Python 3.11.6, Node 24.16, Ollama 0.40.17, and Gemma 4 11.9B Q4_K_M (installed tag `gemma4:12b-it-q4_K_M`). The inference run used GPU acceleration, no thinking, 8,192 context, temperature 0.2, two tool rounds and a 150-second overall deadline. The model tag and configuration stayed the same. No model was downloaded. Token metrics depend on Ollama's response metadata. Native hardware utilization and energy were not sampled over time.

## Comparative behavioral results

The common first 29 fixtures contain 42 assistant turns and 83 checks. Baseline passed 52 checks and the candidate passed 82 on each of three complete runs. The third candidate run also completed all 42 turns with zero unauthorized setting commits. The expanded 42-fixture matrix adds 13 held-out probes, for 57 chat turns and 100 checks per revision. The baseline passed 58 and the candidate passed 97. Both completed with zero harness errors and no unauthorized writes. See the per-fixture counts below. The pass totals are a coverage index across correlated component checks, never an effectiveness score.

| Measure | UX baseline, offline | Candidate, deterministic paths |
| --- | ---: | ---: |
| A2 final fidelity score, starting at 2/8 | 0.5/8 | 8/8 |
| A2 needed controls addressed | 0/6 | 6/6 |
| A2 initially aligned controls changed | 2/2 | 0/2 |
| B2 final score, starting at 2/8 | 7/8 | 7/8 |
| B2 needed controls usefully addressed | 6/6 | 6/6 |
| B2 protected settings staged and applied | 3 | 0 |
| B2 total proposed items, outside rubric in parentheses | 19 (13) | 8 (2) |
| Exact target settings, including manual guidance | 0/8 | 8/8 |
| Correct targeted history recovery | 0/2 | 2/2 |
| Held-out named-setting exclusions | 0/2 | 2/2 |
| Mixed objective, protection, explanation and explicit memory components | 2/4 | 4/4 |
| Scoped preference coexistence and targeted withdrawal | 0/2 | 2/2 |
| Manual A1→B1 onboarding assertions | 5/5 | 5/5 |
| Reverse cross-game analogue assertions | 3/3 | 3/3 |
| Discover intervention assertions | 6/7 | 7/7 |
| Explanation concept-and-grounding checks | 5/8 | 8/8 |
| Explanation turns with no recommendation or goal mutation | 8/8 | 8/8 |
| Review, Apply, history, undo/restage and locks checks | 4/4 | 4/4 |
| Unauthorized chat-time setting changes | 0/42 turns | 0/42 turns |

B2's candidate changes included Medium Global Shadow Quality and Medium Particle Detail, each worth half credit. The setting facts permit concrete trade-offs. The goal test cannot determine whether Low would be better for a given player. High Dynamic Range and Parallax Occlusion were the two proposals outside the eight-item score. The candidate retained Boost Player Contrast and useful existing player shadows. A2 kept high Material Quality and existing Bloom, and addressed the other six controls, including anisotropic filtering, UI quality and cast shadows. No measured FPS or visual improvement follows from these scores.

For A1→B1, actual VALORANT manual changes yielded inspect-only CS2 cards for sensitivity, voice and ping before chat in both revisions. The candidate keeps these behaviors and suppresses treating Undo as new transfer evidence. The three evidence-backed cards reached 3/3 relevant top slots and 3/3 supported-transfer coverage in this fixture. In Discover, both initial cards survived an unrelated volume edit with the same IDs in the candidate. The baseline kept their content and rebuilt both IDs. The context case contained no duplicate settings and the previously dismissed target stayed suppressed. Disabling just the aligned-inspection method in the candidate dropped the objective-switch Discover assertion. That ablation preserves the stable refresh, cross-game and exclusion behavior. See the [ablation evidence](evidence/discover-no-aligned-inspection.json).

A second ablation kept the shared objective parser and SQLite schema but used additive weights for every turn. It passed the same 24 of 25 checks in five selected groups. During the temporary fidelity goal, it additionally staged the FPS counter using the earlier performance objective and saved FPS preference as evidence. The candidate kept that diagnostic out of the proposal while retaining a relevant aligned inspection. This favors precedence for clearly temporary objectives and leaves the earlier additive policy available for weaker goal statements. [Additive ablation evidence](evidence/additive-objective-ablation.json)

The improved shadow comparison explains the difference between overall quality and the light sources that cast dynamic shadows. The frame-rate comparison explains generated frames and display updates with a 240 Hz example. Ambient occlusion mentions contact shading and graphics cost but could still explain a scene-specific contrast with ordinary cast shadows more plainly. The outputs ground conceptual checks in known facts. They leave skill transfer and retention to a human study.

## Representative replay outputs

- **Temporary objective.** The baseline interpreted “I normally prioritize FPS, but tonight I want the game to look nice” as performance and staged three more performance changes. The candidate kept the saved FPS priority and represented Visual Quality as the current goal. The prior competitive draft was marked outdated. The candidate said “I found no additional eligible changes for visual quality” where pending drafts already occupied those controls. Discover supplied an aligned inspection rather than copying pending suggestions.
- **Exact recovery.** After the CS2 Master Volume moved from 0.8 to 0.4, chat resolved the latest live volume transition and staged only 0.8. The subsequent explicit Apply changed one setting. The VALORANT route displayed the earlier 80% and its canonical position for manual editing. Neither recovery reverted the other exact changes.
- **Scope correction.** VALORANT and CS2 kept different priorities for input latency. The CS2 withdrawal removed just the matching CS2 preference. The ambiguous and speculative examples did not persist a preference.
- **Cross-game evidence.** The three onboarding cards displayed manual VALORANT choices and normal CS2 values. The explicit grounded comparison returned a same-DPI hipfire estimate and no config mutation. The reverse mapping and the utility analogy were checked separately.

## Live inference

The stock baseline run completed all 13 scenarios and 16 turns. Actual provenance was 15 Gemma turns and one deliberately unreachable-endpoint fallback. Gemma latency ranged from 16.253 to 147.066 seconds, with a 44.691-second median. There were 16 recorded model invocations and 46 recorded read-tool entries. The suite took 913.9 seconds and produced seven proposals, all still staged at the end. The well-configured case had no staged changes. In the seeded cross-game case, advice included trade-offs and target setting choices. That existing fixture uses a preset history, so it cannot replace the manual-history onboarding replay.

The paired live suite uses identical pilot fixtures, model configuration and scoring in both versions. Model, catalogue rules and fallback are distinct sources in its evidence. A timeout can discard partial internal call telemetry when the graph does not return, so recorded tool and invocation counts are lower bounds for timeout turns.

The paired subset ran nine scenario groups and 12 turns per revision. Baseline used 11 Gemma turns and one fallback, with a 73.9-second median. The experimental implementation used nine Gemma turns, one fallback and two rules turns, with a 42.7-second median. These medians include user-turn time regardless of provenance. Each local scenario was run once per revision. The baseline passed 26 of 35 assertions and the audit implementation passed 33.

| Paired case | UX baseline | Audit implementation |
| --- | --- | --- |
| a2 | Gemma, 70.2 s · 2/8, 0/6 needed settings, 0 proposals, 0 protected commits | Gemma, 91.0 s · 8/8, 6/6 needed settings, 6 proposals, 0 protected commits |
| b2 | fallback, 150.1 s · 7/8, 6/6 needed settings, 19 proposals, 3 protected commits | Gemma, 132.2 s · 7/8, 6/6 needed settings, 8 proposals, 0 protected commits |
| mixed request | Gemma, 74.6 s · 3/4 checks | fallback, 150.1 s · 4/4 checks |
| a1 b1 onboarding | Gemma, 49.9 s · 5/5 checks | Gemma, 43.8 s · 5/5 checks |
| b objective shift | 4 Gemma, 76.6 s median · 6/8 checks | 4 Gemma, 37.2 s median · 8/8 checks |
| c review recovery | Gemma, 144.4 s · 4/4 checks | Gemma, 121.1 s · 4/4 checks |
| combined exact request | Gemma, 73.2 s · 1/1 checks | rules, 0.006 s · 1/1 checks |
| explain ao | Gemma, 38.4 s · 1/2 checks | Gemma, 30.1 s · 1/2 checks |
| explain fps hz | Gemma, 56.6 s · 2/2 checks | rules, 0.006 s · 2/2 checks |

- **Baseline efficiency.** 11 recorded model calls, 34 read-tool entries, 20,461 input and 4,038 output tokens across 11 invocations with token counts. Median observed Gemma turn 73.2 s, maximum 144.4 s.
- **Candidate efficiency.** 9 recorded model calls, 28 read-tool entries, 17,715 input and 3,564 output tokens across 9 invocations with token counts. Median observed Gemma turn 43.8 s, maximum 132.2 s.

Protected categories remained unchanged after the candidate B2 Apply. The baseline B2 reached the same rubric total through the deadline fallback, with three excluded audio changes. Both candidate pilot goals completed using Gemma, with six grounded changes for A2 and eight for B2.

The mixed candidate request used the fallback after its deadline. It staged ten performance suggestions, explained ambient occlusion and saved the user's explicit visibility preference only. Baseline Gemma explained the setting but staged nothing and wrote both visibility and performance as durable preferences, even though performance was the current request.

In the temporary goal journey, candidate Gemma preserved the durable FPS preference, kept the earlier draft pending with an outdated-goal warning, and surfaced an aligned Visual Quality inspection. Baseline Gemma recognized the visual objective in chat, while Discover still offered to disable Cast Shadows for performance. Candidate prose referred to settings the player had ‘previously adjusted’ even though the prior draft was still pending. This is a remaining semantic grounding issue.

Both ambient-occlusion replies conveyed the shadow-depth effect and potential rendering cost, and neither returned the structured setting link required by the rubric. This is a missed opportunity to connect understanding to the canonical menu. The combined exact request succeeded in both revisions, taking 73.2 seconds with baseline Gemma and 6 milliseconds on the candidate rules path.

Chat-time committed setting mutations remained 0/12 for baseline and 0/12 for the audit implementation. The A2 improvement is supported by a same-model pair. The broader latency and reliability comparison has too few runs to generalize. [Baseline local evidence](evidence/baseline-local.json) · [Candidate local evidence](evidence/candidate-local.json)

## Limits

The case suite uses only two catalogues and English synthetic prompts. A pass can establish machine-readable routing, option validity and state change. Discover novelty uses available histories and known inspection controls as proxies, and there is no participant familiarity label to calculate behavioral novelty precision. Open goals, hard exclusions and previous-value references outside the bounded grammar need further semantic evaluation. This run does not estimate actual player trust, usability, learning, FPS, latency or image quality. Broad live inference is the most expensive part of the task and needs further repeats before making tail-latency claims. The held-out “Set my volume to 40% for tonight” was treated as an unsupported exact value phrase, so it did not stage. “I always use push to talk” did not yield a voice-mode fact. The candidate saved the bounded small-green crosshair instruction and passed the distinct hold-out for not creating durable memory from tentative “remember” phrasing.


## Per-fixture deterministic evidence

The counts below give passed assertions divided by assertions executed. A case with zero local model calls still exercises actual server behavior through the API. Complete outputs, flags, explanations, and review decisions are in [baseline evidence](evidence/baseline-fallback.json) and [candidate evidence](evidence/candidate-fallback.json).

| Scenario | Split | Baseline | Candidate |
| --- | --- | ---: | ---: |
| a1 b1 onboarding | project | 5/5 | 5/5 |
| b objective shift | project | 5/8 | 8/8 |
| a2 | project | 2/4 | 4/4 |
| b2 | project | 3/5 | 4/5 |
| a3 a4 exact recovery | project | 0/6 | 6/6 |
| b3 b4 exact recovery | project | 0/6 | 6/6 |
| c review recovery | project | 4/4 | 4/4 |
| e already aligned | project | 3/4 | 4/4 |
| mixed request | development | 2/4 | 4/4 |
| exclude vsync | holdout | 0/1 | 1/1 |
| exclude shadows | holdout | 0/1 | 1/1 |
| combined exact request | holdout | 0/1 | 1/1 |
| memory scope correction | holdout | 0/2 | 2/2 |
| reverse analogues | holdout | 3/3 | 3/3 |
| discover events | development | 6/7 | 7/7 |
| navigate minimap | holdout | 1/1 | 1/1 |
| navigate cs2 audio | holdout | 1/1 | 1/1 |
| ambiguous preference | development | 1/1 | 1/1 |
| speculative preference | holdout | 1/1 | 1/1 |
| hypothetical frame quality | holdout | 1/1 | 1/1 |
| model unavailable | development | 1/1 | 1/1 |
| protected sensitivity statement | holdout | 1/1 | 1/1 |
| recovery with no change event | holdout | 1/2 | 2/2 |
| numeric value out of range | holdout | 1/2 | 2/2 |
| already aligned exact toggle | holdout | 1/2 | 2/2 |
| direct shadow navigation | holdout | 1/1 | 1/1 |
| tentative memory wording | holdout | 0/1 | 1/1 |
| explicit crosshair style | holdout | 0/1 | 1/1 |
| no cross game inference from undo | holdout | 0/1 | 1/1 |
| protect after recommendation | holdout | 0/1 | 1/1 |
| exact for tonight | holdout | 1/2 | 1/2 |
| clear objective in chat | holdout | 0/1 | 1/1 |
| visibility over graphics | holdout | 0/1 | 1/1 |
| voice mode habit | holdout | 0/1 | 0/1 |
| explain aa | project | 2/2 | 2/2 |
| explain ao | project | 2/2 | 2/2 |
| explain af | project | 1/2 | 2/2 |
| explain vsync | project | 2/2 | 2/2 |
| explain reflex | project | 2/2 | 2/2 |
| explain shadows | project | 1/2 | 2/2 |
| explain fps hz | project | 1/2 | 2/2 |
| explain diagnostic | project | 2/2 | 2/2 |
