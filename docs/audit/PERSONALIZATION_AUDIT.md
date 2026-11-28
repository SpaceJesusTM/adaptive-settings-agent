# Personalization audit

## Existing strengths and where they break

GamePlan already separates session goals, saved priorities, remembered facts, live settings and committed history. `observe_setting` labels manual edits, applied suggestions, Undo, scenario seeds and untouched defaults. `build_observed_summary` presents discrepancies and tentative patterns. Profile edits and evidence are visible in System Understanding, and a new objective can mark earlier proposals outdated. These are useful primitives for correction and cross-game transfer.

Three baseline decisions undermine those distinctions. The profile replaced preferences by dimension and lifetime across both games. Weight aggregation treated place of origin as evidence of transferability, including game-specific statements. Multiple layers made their own optimistic interpretations of one utterance, and a valid model-generated memory action could be written without direct support. An accepted suggestion or restored value was labeled by origin but could trigger onboarding as deliberate evidence.

## Compared approaches

| Approach | Observed or expected result | Decision |
| --- | --- | --- |
| Baseline additive dimensions and model-proposed explicit actions | Low integration cost, good manual evidence display and common broad tuning. Scope collisions and objective contamination reproduced. | Keep catalogue dimensions for retrieval and retain explicit profile controls. |
| Scoped SQLite records and shared immediate objective | Separately preserve objective narration, salience dimensions, game applicability, and protected setting IDs. Independent fixtures can verify which value, game, source and action the system used. | Candidate. |
| Full free-form unified memory and LLM extraction per interaction | MAESTRO shows why shared hard and soft criteria matter. LangMem and Mem0 illustrate treatment of revisions and retrieval. A flexible extractor could handle paraphrases better. The local latency, correction behavior and retrieval benefit are unmeasured. | Defer a larger memory system. |
| Treat behavior as automatic durable preference | One edit can be meaningful evidence for inspection. Accept, reject, Undo and platform defaults all have plausible interpretations other than stable taste. | Reject automatic promotion. |

The chosen implementation uses `agent/objective.py`, `ProfileService.applicable_preferences` and `ProfileService.prioritize_objective`. Existing rows keep their original behavior. Scoped new rows supersede records within their own scope and can coexist across games. A specific record overrides the same-lifetime global dimension for its game. A clearly temporary or directed objective overrides incompatible weights for that task while a weaker goal can still lead to a retained trade-off. Ending the goal restores access to saved priorities. Only direct, supported memory instructions persist automatically. Removal by chat is restricted to a uniquely identified dimension and scope. The existing panel remains available for inspect, confirm and remove.

## System Understanding

The panel's job is to answer four practical player questions. What goal are you using now? Which remembered priorities apply here? Which observed settings or actions contributed to a suggestion? How can I correct it? The candidate displays protected settings with the current goal and shows game applicability separately from where a preference was recorded. Observations and evidence stay distinguishable from active preferences. Chat and Discover still need to expose sufficient local evidence so the panel can remain secondary.

A confirmation chip is useful when the scope is ambiguous. A general note about crosshair shape or informal relative wording may need explicit follow-up, while a literal push-to-talk key or priority can be saved from bounded wording. The player should be able to remove a mistake quickly, and nothing about accepting a setting bundle should update a lasting priority. The comparison tests cover temporary conflict, correction and removal, conservative ambiguity and speculation, and mixed utterances. [Observed outcomes](EVALUATION_RESULTS.md)

## Cross-game analogues

| Family | Relationship and evaluation | Assistance boundary |
| --- | --- | --- |
| Voice and ping bindings | Functional equivalents with different team/party routing and independent key conflicts. Manual A1 history supports three inspection opportunities, including these two. | Show source key, destination key, and provenance. Manual rebind remains the player's choice. |
| Movement and hold/toggle | Shared movement concepts. Defaults, action names, secondary binding conventions and ergonomics differ. | Explain the mapping and route to destination. Transfer only an explicitly applicable abstract preference. |
| Mouse sensitivity | Physical quantity under assumptions. For equal DPI and default yaw, VALORANT→CS2 is (s 	imes 0.07/0.022) and the reverse is (s 	imes 0.022/0.07). The forward 0.35→1.11 and reverse 1.27→0.40 paths are exercised. | CS2 default yaw is represented as 0.022 and the VALORANT factor is a community-calibrated assumption used by the simulator. Scaling preserves approximate hipfire turn distance given the assumptions. ADS, zoom, field of view and subjective feel remain game-specific. |
| Crosshair | Some color/size characteristics have analogues with different units, style presets and dynamic behavior. | Explain approximate visual intent and direct the player to previews. Keep numeric transfer and code conversion manual. |
| Utility | Abilities and grenade controls are loose workflow analogues. | Describe the actions and differences. No blind value copying. |
| Graphics and visibility | Abstract priorities can transfer using target-catalogue details. Player shadows and clarity effects have different meanings. | Resolve target settings against current objective, applicability and hardware. |
| Audio and HUD | Some goal-level analogues such as spatial cues and decluttering. Audio mixes and layout ranges are game specific. | Explain and inspect supported mappings. No universal conversion of levels, HUD or positional audio. |

The estimate follows `convert_hipfire_sensitivity` and a same-DPI count-to-angle invariant. A changed CS2 yaw or mouse DPI changes the ratio. Neither game was run for this study. The published CS2 game dump lists separate yaw and zoom factors. The VALORANT factor is corroborated by a public aim trainer implementation, with no first-party calibration established in this audit. [CS2 convar dump](https://github.com/SteamDatabase/GameTracking-CS2/blob/master/DumpSource2/convars.txt) · [AimTrainer reference](https://github.com/CHINOBv/AimTrainer) · [GamePlan cross-game implementation](../../backend/app/domain/cross_game.py)

Onboarding supplies evidence that was actually observed in the simulator. A confirmed durable preference can drive target-game ranking if applicable. Applying an earlier suggestion or Undo stays in provenance and no longer qualifies as a new manual source for proactive carry-over. The explicit comparison tool can still describe current values with their origin. A capability to surface a plausible inspection is separate from evidence of useful transfer in play.
