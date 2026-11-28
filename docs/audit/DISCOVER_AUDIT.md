# Discover audit

Discover serves optional, timely exploration of settings the player may overlook, including in a newly visited game. Chat answers a declared request, Changes is where the player reviews edits, and Pinned provides persistent user-selected shortcuts. Discover adds value when it introduces a new, supported inspection or a worthwhile follow-up without moving or hiding settings. Quiet state is a valid outcome.

## Baseline policy

`RelevantNowService._collect_candidates` reads a profile weight vector, companion rules from recent change batches, onboarding evidence and a simulated context event. It combines fixed-priority buckets, deduplicates by setting ID and limits the view to four cards. `rank_candidates` uses catalogue hints with goal weights, hardware, current values, locks and pending settings. `build_onboarding_cards` makes mostly inspect-only cards about sensitivity and voice, with ping when evidence exists. `get` annotates persisted cards and compares fresh candidates with the original snapshot.

This architecture already gives stable reads, state-aware cards and direct navigation. It offers useful read-only checks from actual prior manual changes. Problems emerge on writes: `refresh` always minted new IDs, the dismissal key was the whole weight vector, and a few hard-coded buckets could occupy Discover when an explicit new goal already had a plan. Any candidate with positive score could qualify, and a change-only goal ranker could go empty despite a useful aligned concept.

## Candidate policy

1. Keep the same bounded deterministic generator and apply current objective exclusions. Suppress incompatible follow-up changes and generic onboarding that is unrelated to the active objective.
2. Keep existing cross-game check eligibility for confirmed facts, truthful synthetic scenario data and manual history. Give applied suggestions and Undo their own evidentiary treatment.
3. Reuse card identity when action, target, explanation and trigger evidence still match. Leave the snapshot alone on irrelevant changes. During a session, suppress the same kind, setting, target and rationale dimension after dismissal, even if an unrelated preference changes. Companion and onboarding resolutions retain their own evidence or check identity.
4. Offer one inspect-only aligned setting when an explicit goal exists and there are no other eligible cards, using current values and a catalogue hint. Skip settings with a deliberate change recorded. This is an approximation of unfamiliarity because the application does not track reliably whether a person has read or understood a setting.
5. Respond to material events and current goal changes. Idle reads remain passive. User refresh and dismissal keep direct control with the player.

## Comparison and decisions

The deterministic baseline, stable candidate policy and an intermediate round without the aligned inspection provide a practical ablation. Both policies produced the three supported manual cross-game checks. In the intermediate round, the new visual goal was present but its Discover view was empty because the available changes had already been staged. An aligned inspection probes educational Discover without duplicating a staged change. See the [paired results](EVALUATION_RESULTS.md) for intervention and miss counts.

No additional model calls were introduced for Discover. An LLM ranking experiment is plausible where lexical goal understanding is the bottleneck, but the current cases first benefit from stable state and clearer eligibility. It would need to improve useful unfamiliar-setting coverage without increasing contradictions, churn, latency or over-personalization. Reinforcement learning is premature when interruption cost and post-card learning are unmeasured.

The technical replay checks duplicate cards, stable passive reads, stable identities after an unrelated edit, context responsiveness, evidence-backed onboarding, aligned behavior and dismissal. It cannot decide which settings a player has never noticed or whether a card improved independent use. The aligned inspection adds a testable mechanism for a later participant comparison.
