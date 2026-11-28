# Evaluation results

## Comparative evidence

The continuation runner uses the public simulator API, a temporary SQLite database for every scenario and synthetic game values. Evaluation rubrics stay outside the assistant prompt. Versions are original comprehensive UX **c75d81e**, first audit **6386dd2** and overnight candidate. The first-audit runner remains frozen. The initial overnight runner had a Discover fixture that could submit existing values as no-ops. Version 2 makes actual prior edits and checks a different inspection target. It adds a late visual paraphrase and reuses the frozen goal-shift fixture. Compare scores within the same fixture version.

| Version | Continuation v2 offline checks | Cases and turns | Scope |
| --- | ---: | ---: | --- |
| A. Original comprehensive UX, c75d81e | 31/58 | 25 cases, 25 turns | Legacy offline |
| B. First audit, 6386dd2 | 39/58 | 25 cases, 25 turns | Legacy offline |
| C. Overnight presentation defaults | 54/58 | 25 cases, 25 turns | Existing Discover and legacy routing |
| C. Overnight utility policy | 55/58 | 25 cases, 25 turns | Adds the novel, protected-video inspection |

The final candidate passed **99/100** on the untouched first-audit fallback suite across 42 scenario groups and 57 chat turns. The remaining check is B2's all-eight criterion. Its 7/8 keeps both tested visibility aids. Two rubric rows each earn half credit because the configuration retains medium shadows and particle detail as trade-offs. That rubric measures fixture-specific suitability and does not establish a universal optimum.

No candidate matrix run had a harness error or an unsolicited committed setting change during chat. The benchmark intentionally executes selected proposals and labelled manual setup through separate API calls. The dated A baseline shows a protected audio change when the old B2 proposal was applied. The current suite verifies 409 when Apply encounters a protected old item, an atomic mixed-selection test, and no writes on an ambiguous or explanation-only ask. Baseline safety failures count even when code otherwise behaved as expected.

## Repeated live-model comparisons

These are three repetitions per scenario, using the same installed Gemma tag, fixture states, sampling configuration and M4 hardware. First-audit provenance is reported by the frozen runner. Compact runs used **4a614b4**, before follow-up decisions about mixed outcomes and window labels.

| Frozen scenario | First audit | Compact |
| --- | --- | --- |
| A2. Fidelity | Pilot scores 8, 8, 8. Checks 12/12. | Pilot scores 7, 8, 8. Checks 11/12. The first run skipped UI Quality. |
| B2. Competitive | Pilot scores 7, 7, 7. Checks 12/15. | Pilot scores 7, 7, 7. Checks 12/15. One repair increased latency. |
| Mixed request | 12/12. Two model results and one fallback after 150 s. | 11/12. Three model results. One had a valid explanation and memory update but staged zero recommendations. |
| Ambient Occlusion | 3/6. Correct topic in all three. Canonical link in one. | 6/6. Canonical link in all three. |

The A2 and B2 pilot checks include committed changes after explicit Apply. A2 starts at 2/8 in the live pilot. B2 protects control, crosshair, audio, resolution and aspect ratio, and counts visibility aid retention independently. The [performance profile](AGENT_PERFORMANCE.md) reports tokens, call counts, phases and model-side limitations. [Repeated measurements and representative outputs](evidence/live-matrix.json)

## Representative outcomes

| Case | First audit result | Overnight result and provenance |
| --- | --- | --- |
| Mixed change, exact exclusions, Ambient Occlusion explanation and memory | No performance proposal, no canonical explanation, and an extra prioritized dimension. | All four components correct in fallback and in the measured legacy, compact and semantic probes. The model path and checked catalogue both contribute. |
| “I can give up a few frames” to see opponents | FPS treated as a goal and protected MSAA changed in the draft. | Keeps visibility primary and preserves explicit exclusions. The dimension correction precedes inference. |
| Temporary values and voice habit | Failed the three exact temporal changes and the CS2 habit fixture. | All three temporal variants preserved scope and exact meaning. VALORANT's manual-only volume receives canonical guidance. The voice mode is a CS2-specific explicit fact. |
| “Put my master volume back where it was before I touched it” | No restoration in the tested wording. | Explicit Apply restores 0.43 to the actual prior 0.81 and leaves the other edit. Catalogue rules. |
| Original draft predates protection | Direct Apply returned 200 and changed Reflex from Disabled to Enabled. | Apply returned 409 with no eventual diff. Direct manual control remains. |
| Consecutive independent manual choices versus equivalent accepted plan | The cross-session observation disappears. | A tentative visibility signal appears only after separate manual evidence. Confirmed preferences stay empty in both. |
| Protected-video discovery after real edits | An FSR inspection or no appropriate unfamiliar trade-off. | Utility reports Global Shadow Quality for comparison with Dynamic Shadows. Default policy lacks this targeted inspection. Neither stages a protected setting. |
| Fresh CS2 from actual VALORANT edits | Cross-game freeze passes. | Both overnight policies pass all five checks. Gemma legacy also passed once, using the observed 0.40 and equal-DPI 1.27. |
| Unfamiliar visual phrasing | Rules fail to infer a useful change. | The final optional semantic variant staged eligible proposals in 4/4 repeated live turns across the two visual inputs. Default legacy staged none in its matched probes. Earlier hybrid attempts show the gap between topic detection and grounded options. |
| Pending Reflex question | Could not match the setting in the wording. | Reads Disabled as current and Enabled as pending, with a link. Catalogue rules. |

The continuation cases were authored independently of the final integration. Some were used to diagnose or refine bounded rules, so their final outputs are regression evidence. The later floor-pattern wording is tagged separately. The live tests use a handful of synthetic objectives on two supported catalogues. They cannot measure user learning, study effects, real FPS, or preference ground truth. [Case-level offline results](evidence/offline-matrix.json) · [Semantic ablations](SEMANTIC_UNDERSTANDING.md)

## Run the comparisons

From the overnight checkout, use the project Python environment. Set **ORIGINAL** and **FIRST_AUDIT** to checkouts at the cited commits. Command output goes to ignored scratch paths. The comparative cases, Apply policy, and exact model value are in the runners.

```sh
python scripts/run_overnight_benchmark.py --repo "$ORIGINAL" --mode fallback --out data/local/original-v2.json
python scripts/run_overnight_benchmark.py --repo "$FIRST_AUDIT" --mode fallback --out data/local/first-audit-v2.json
AGENT_DISCOVERY_POLICY=current python scripts/run_overnight_benchmark.py --repo . --mode fallback --out data/local/current-v2.json
AGENT_DISCOVERY_POLICY=utility python scripts/run_overnight_benchmark.py --repo . --mode fallback --out data/local/utility-v2.json
python scripts/run_audit_benchmark.py --repo . --mode fallback --out data/local/frozen-regression.json

export OLLAMA_MODEL=gemma4:12b-it-q4_K_M OLLAMA_BASE_URL=http://127.0.0.1:11434
python scripts/run_audit_benchmark.py --repo "$FIRST_AUDIT" --mode local --cases a2 b2 mixed_request explain_ao --repeat 3 --out data/local/first-live.json
AGENT_REASONING_MODE=compact python scripts/run_overnight_benchmark.py --repo . --mode local --cases live_a2 live_b2 frozen_mixed frozen_explain_ao --repeat 3 --out data/local/compact-live.json
AGENT_REASONING_MODE=semantic python scripts/run_overnight_benchmark.py --repo . --mode local --cases current_visual distant_textures --out data/local/semantic-live.json
```

For the published compact measurement, use **4a614b4** as the value of **--repo**. The [hardware procedure](AGENT_PERFORMANCE.md) records exact flags and desktop setup. Run local series sequentially. A fixture can produce a labelled fallback after attempting inference. When inspecting results use **source**, **fallbackReason**, **modelCalls**, **phaseTimingsMs**, plan coverage and the actual staged and committed values.

## Regression suite

- Backend pytest, 125 passed, including later-batch timeout, mid-inference manual revision and atomic stale protection.
- Frontend Vitest, 28 passed. Production build passed.
- Chrome Playwright, 26 passed, including the existing 25 menu and participant journeys and the new stale-proposal review.
- Frozen fallback runner, 42 scenarios, 99/100 checks and zero harness errors. The reproduced B2 incremental trade-off remains visible.
