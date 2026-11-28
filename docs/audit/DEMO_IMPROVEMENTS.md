# Demonstration guide

The audit worktree uses an independent SQLite file and loopback ports. Install the existing locked dependencies as in the [project setup](../../README.md). In the audit worktree's ignored `.env` use these values, with `OLLAMA_MODEL` set to the installed Gemma tag for live turns.

```dotenv
CSC2524_DB_PATH=data/local/audit-demo.db
BACKEND_PORT=18765
FRONTEND_PORT=15173
OLLAMA_MODEL=gemma4:12b-it-q4_K_M
```

Run `python scripts/dev.py --serve` and open the app at port 18765. Use Experimenter controls to select the required condition, AI mode and scenario. Run each walkthrough on fresh simulation state or restore a synthetic checkpoint. Keep the A1 history when moving to B1.

## A. Start a second game using actual prior choices

1. Start the default VALORANT simulation in baseline mode. Set aim sensitivity to 0.40, Team Voice Push to Talk to B and Ping to X through the canonical controls.
2. Switch to fresh CS2 in adaptive mode. Open Discover before using chat. Inspect the source evidence on the voice, ping and sensitivity cards. Check that the CS2 inputs retain their starting values.
3. Ask for the equivalent of the VALORANT sensitivity in CS2. The cross-game comparison shows approximately 1.27 at equal DPI and its limitations. Jump to the canonical control and leave it under manual control. Open System Understanding and inspect the manual observation source.

## B. Change the objective without rewriting preferences

1. In VALORANT say “Remember that I usually prioritize high FPS.” Inspect the saved preference in System Understanding.
2. Ask for smoother FPS and lower input lag. Inspect the resulting draft and leave it pending.
3. Say “I normally prioritize FPS, but tonight I want the game to look nice.” Inspect the current visual-quality goal, the still-saved FPS preference, the old draft warning and the updated Discover view. An aligned card can explain what already fits when there is no eligible new edit.
4. Inspect and reject old draft items you no longer want. Clear the goal in System Understanding or say “Clear my current goal.” The saved FPS preference becomes relevant again.

## C. Review a goal-based CS2 proposal

1. Use the B2 fixture from the API benchmark for exact pilot comparability. Request practical frame rate, responsiveness and enemy visibility while preserving personal controls, audio, crosshair, resolution and aspect ratio.
2. Open Changes. Inspect ambient occlusion, visit its canonical position and view the trade-off. Edit or exclude a proposed item before Apply. Confirm the protected values and then explicitly apply the selected items.
3. Open History, inspect planned versus applied values and Undo. Review and restage the earlier batch, then check that the committed values stay at their post-Undo state until another Apply.

## D. Perform exact changes and recover one value

1. In CS2 ask “Enable rotating radar, set Show ping to Always, and set Master Volume to 40%.” Use the corresponding exact fixture to ensure starting values differ. The catalogue-backed path stages the literal values. Apply in Changes.
2. Ask “Set horizontal HUD Edge Position to 0.85.” Follow the canonical HUD Edge Positions guidance, change only Horizontal Adjustment, and select Done.
3. Ask “Restore the volume to what it was before those changes, but keep everything else.” Review the single recorded prior value and apply just that volume. In VALORANT, Overall Volume is a manual-only control and the assistant supplies its prior value and location.
4. Use the history panel to show the committed edits and their sources.

## E. Observe a quiet Discover state

1. Start the well-configured fixture. Open Discover, make an unrelated manual edit or ask an ambiguous question, and compare the active cards. A cold start can show read-only checks. An ambiguous message should not force a setting proposal.
2. Trigger a simulated frame-drop event and dismiss the first useful proposal. Change the simulated context, then return to frame drops. The same target remains suppressed within the session.
3. Introduce a meaningful graphics objective. Confirm that any new candidate responds to the objective and leaves canonical navigation intact.

## December 1 presentation

A and D are short, reproducible examples of evidence-aware personalization and retained authority. B shows the HCI research question directly. Explain C's scenario and include a verified response or a deterministic replay if live latency would take too much of the talk. Label the response source in every example. Report the A2 or B2 score as an eight-item simulated task proxy. Human learning and actual FPS or latency need later measurement.

The [evidence report](EVALUATION_RESULTS.md) links complete API traces for these journeys. The existing browser suite verifies the rendered workspace, canonical navigation, detachment, history, explicit Apply and the HUD modal.
