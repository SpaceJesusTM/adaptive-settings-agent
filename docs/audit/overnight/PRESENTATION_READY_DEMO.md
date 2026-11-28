# December 1 presentation demo

The 1:45 prerecorded video follows one player from familiar VALORANT controls to an unfamiliar CS2 menu. It follows the [presentation and pilot mapping](../PROJECT_REQUIREMENTS.md). The demo builds on actual simulator edits. Use fallback mode for the goal and review scenes to make the narration reproducible. Use the catalogue route for the Ambient Occlusion comparison. Give each scene its actual provenance in a brief caption.

| Time | Screen and action | Narration |
| --- | --- | --- |
| 0:00–0:23 | Baseline VALORANT. Use the canonical controls to set sensitivity to 0.40, Team Voice Push to Talk to B, and Ping to X. Cut to fresh adaptive CS2 and open Discover. | “I set up VALORANT the way I normally play. In CS2, GamePlan uses those settings to suggest three controls worth checking. Each card tells me where its evidence came from, and CS2 still has its starting values.” |
| 0:23–0:43 | In CS2 Chat ask “What CS2 sensitivity matches my VALORANT sensitivity?” Show approximately 1.27 and jump to Mouse Sensitivity. | “The conversion gives me a starting point if I keep the same mouse DPI. I can inspect the original CS2 control and decide whether to use it.” |
| 0:43–1:04 | Ask “Are those little dark creases around corners from ambient occlusion or the same shadows that players cast? Show me where to inspect ambient occlusion without changing anything.” Follow the link. | “This distinction matters when I tune for visibility. Ambient Occlusion adds depth at edges and contacts. Dynamic Shadows controls moving shadows, which can give away a player indoors. I can see the two controls in their original menu.” |
| 1:04–1:32 | Cut back to the saved VALORANT checkpoint for the authority scene. Ask for smoother FPS and lower input lag. Open review. Say “Keep VSync unchanged.” Deselect another item, Apply and open History. | “I asked for smoother play. When I protect VSync after the draft appears, that setting becomes unavailable in the review tray. I choose what gets applied, and History records my selection and gives me an Undo.” |
| 1:32–1:45 | Show the current objective in My Priorities and the retained canonical control. | “GamePlan connects unfamiliar controls to the player's goals, explains the choice, and leaves the final decision with the player. The study tests what players can find and explain on their own.” |

DG1 appears in the navigation and onboarding scenes, DG2 in the contrastive explanation, DG3 in review and Undo, and DG4 in the evidence-driven cross-game transition and the later correction.

## Rehearsal and checkpoints

Start an isolated checkout with the existing locked dependencies. Use an ignored database and loopback ports in its environment. Run the normal app for the browser recording and the public API harness for the synthetic repeat. Launching the harness creates independent temporary databases and leaves the recording database available for manual edits.

```dotenv
CSC2524_DB_PATH=data/local/overnight-demo.db
BACKEND_PORT=19765
FRONTEND_PORT=16173
AGENT_REASONING_MODE=legacy
AGENT_DISCOVERY_POLICY=current
```

```sh
python scripts/dev.py --serve
python scripts/run_overnight_benchmark.py --repo . --mode fallback \
  --cases onboarding_from_real_edits explain_ao demo_goal_shift pending_protection \
  --out data/local/demo-rehearsal.json
```

1. **Behavior before chat.** Use the default starting scenario. For exact benchmark parity, add light cyan crosshair, Medium Texture Quality and Overall Volume 65 in VALORANT. Preserve this history while switching to CS2. Discover shows three canonical inspection cards grounded in manual edits. The chat comparison uses the same observed 0.40 and shows **1.27** as an equal-DPI analogue. Mark the voice inspection checked and verify the CS2 options still have their original values. The browser suite exercises both games and original navigation.
2. **Educational short path.** From default CS2, ask the creases-versus-player-shadows question from the table. The rules output begins “Ambient occlusion adds shading near contacts and in crevices, helping surfaces look less flat.” Open **Video → Advanced Video → Presets → Ambient Occlusion**. No review item is created. For a state comparison, stage NVIDIA Reflex through the review API fixture, then ask “Did I already enable NVIDIA Reflex Low Latency or is that just waiting in the review tray?” The reply reads **Disabled** as current and **Enabled** as pending.
3. **Changing goals.** In fresh VALORANT say “Remember that I usually prioritize high FPS.” Ask “Help me get smoother FPS and lower input lag.” Keep that draft open. Say “I normally prioritize FPS, but tonight I want the game to look nice.” The active goal becomes visual quality, the saved performance priority remains, and the old draft reports an outdated goal. Inspect Discover. Clear the temporary goal in My Priorities and show the saved performance priority remains. This is a separate rehearsal and can substitute for the final authority scene if the talk needs a longer DG4 treatment.
4. **Authority review.** In fresh VALORANT use the performance request from step 3. VSync starts On. From the old review ask “Keep VSync unchanged.” The VSync checkbox is disabled and cleared, the other choices remain available, and Apply leaves VSync On. Visit History and Undo the selected batch. The browser journey uses these interactions. The independent CS2 API scenario attempts to apply an older protected Reflex item and receives HTTP 409. A later direct manual edit remains available.
5. **Restraint.** Load the labelled **well_configured_competitive** fixture for a separate check. Ask for a competitive setup. The adaptive view can surface already-aligned settings with no forced changes. In a fresh session, “Put that back how I had it” asks for clarification without a proposal.
6. **Optional Discover experiment.** Enable the utility policy in an isolated session, set CS2 contrast and Dynamic Shadows to Disabled/Sun Only, and then edit both back to Enabled/All. Ask for visibility in dark areas while leaving video settings untouched. Use the resulting inspect-only option and its evidence. The current policy is preferred for the recorded presentation because the utility evaluation is still narrow.

The fallback and catalogue turns use the same application paths the user normally runs. The benchmark scripts are available for rehearsal and independent checks. A live-model cut can use a recorded actual Gemma response for A2 or B2, with inference time condensed in editing and identified as such. The frozen benchmark scores simulated suitability, and the demo does not need to claim a change in actual FPS or participant learning.
