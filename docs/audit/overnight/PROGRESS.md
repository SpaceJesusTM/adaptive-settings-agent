# Overnight audit progress

The isolated branch `audit/overnight-agent-intelligence` starts from the pushed first audit at `6386dd20ab3d99c83a5608219b2eb501ad0b107a`. The verified original checkpoints are `c75d81e2e726fd14e26a3f31e6961f925cb097f4` and `ff6874eacbac720444f86ba22ec0b050c53ba937`. Runtime configuration and SQLite files are ignored. The audit uses ports 19765, 19766 and 16173. Model comparisons use the already installed Gemma tag, with one inference run active at a time on the M4 Mac with 24 GB of unified memory.

## Hypotheses before candidate runs

- Enforce current setting protections at explicit Apply time, including for proposals created before a correction. Test the actual transaction and browser review path.
- Compare a compact catalogue-grounded selection path and a structured semantic stage against the existing composition graph. Evaluate decision quality independently of hardware-specific latency.
- Prefer independently supported, inspectable evidence from repeated manual behavior over unconfirmed automatic memory. Rank relevant Discover candidates by useful information and abstain when evidence is weak.
- Attach canonical links to grounded explanation requests in the backend and compare a small contrastive explanation strategy on setting distinctions.

Baseline reproduction used the original and first-audit checkpoints. The first-audit runner and reports remain frozen.

## Checkpoints

- **cba600a** reproduced and blocked stale Apply, added canonical link resolution and implemented read-only contrastive explanations. Verified the new protection through API calls and the browser review journey.
- **4a614b4** added configurable compact selection, optional interpretation, telemetry, late-batch retention, cross-session observation, and the first utility policy. Ran four frozen live fixtures three times on the M4.
- **fd1efb7** restored the immediate visibility of a single manual edit. Split accepted costs from the benefit being requested, preserved all bounded mixed-turn components, and restored concrete context-event suggestions under utility. Added tests for an in-flight manual revision and a real asynchronous timeout in the second batch.
- **aa2d317** restricted semantic interpretation to the current game menu, requiring evidence of an actual request for options to stage. Strengthened Discover novelty by making two real edits instead of submitting default values as no-ops.
- **066643f** repeated the original, first-audit and overnight comparisons using the revised fixture and added a new implicit visual paraphrase and the goal-shift rehearsal.
- **3b465f8** made the utility policy prefer a meaningful comparison with an already encountered control and recovered one aligned inspection when other utility candidates are exhausted.

- **5f41801** grounded the interpretation prompt in nearby canonical menu entries and the goal taxonomy. It identified the visual-quality topic while failing evidence binding in both probes.
- **bc2e31d**, **a59f4fc** and **737ea17** tested numbered evidence, made selections required, and used explicit options requests to corroborate staging. Valid advice and an eligible staged setting appeared after requiring clause selections.

The benchmark reports track the exact revision and experimental mode for each run. Earlier utilities had negative results. Phase measurements and mock timeout tests distinguish inference cost and the persistence of usable partial work. Only the overnight worktree holds these changes. The first audit and both original branch tips are preservation checkpoints.

- The final semantic revision passed two runs each of the two visual requests. All four staged usable, protected proposals. Its 48.4-second median is a Mac measurement.
- The preserved first-audit suite passed 99/100. The overnight continuation matrix passed 54/58 with the stable defaults and 55/58 with utility. Backend, frontend and Chrome finished at 125, 28 and 26 tests passed, respectively.
