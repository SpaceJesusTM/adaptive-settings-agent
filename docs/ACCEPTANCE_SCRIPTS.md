# Manual acceptance scripts

Each script starts from **Study controls → Full reset** of the named scenario. “Pass” criteria are observable in the
UI; most are also covered by automated tests (named in brackets).

## 1. Find an unfamiliar setting (both conditions)
* Scenario `default`, condition A. Task: “Find where to change how much of the map the minimap shows.”
* Use the tabs or the search box (type *minimap*).
* **Pass:** the *General > Map > Minimap Zoom* row is shown in place and highlighted; no rows moved.
  [e2e: *search takes the user to the canonical row*]

## 2. Understand an explanation (condition B)
* Ask *“What does anti-aliasing do?”*.
* **Pass:** an explanation card shows *What it does* from the catalogue (with source) separately from the assistant’s
  wording; *Show in settings* highlights *Video > Graphics Quality > Anti-Aliasing*. Nothing is staged or changed.

## 3. Apply a goal-based change set (condition B)
* Ask *“I'm getting frame drops in VALORANT and want smoother competitive play. What should I change?”*.
* Check each card: current → proposed, why (goal), what it does, trade-offs; *Why this?* lists the evidence.
* **Stage all**, edit one staged value, **Apply selected changes**.
* **Pass:** values change only after Apply; *History* shows *AI proposed · user applied* (or *Fallback suggestion ·
  user applied* in fallback mode) with before/after values; *Undo* restores them. [e2e: *suggestions do nothing until
  staged and applied*; pytest: `test_proposals.py`]

## 4. Reject a suggestion
* From any suggestion set, stage, then **Reject selected** (or dismiss a *Relevant now* card with a reason).
* **Pass:** no value changes; a dismissed card is not reinserted on refresh unless goals/preferences change.
  [pytest: `test_reject_changes_nothing…`, `test_relevant_now_hold_rule_and_dismissal`; e2e: *does not reinsert*]

## 5. Locks
* Lock *VSync* (row 🔓). Ask for lower input latency.
* **Pass:** VSync is not suggested (or appears under *removed by safety checks: locked*); staging it via the API yields a
  `blocked` item; a bundle containing a setting locked after staging is refused as a whole. [pytest + e2e]

## 6. Transfer preferences across games
* Scenario `valorant_history_new_cs2` (or: in VALORANT save *low input latency* and *clear player visibility* as
  lasting preferences, then switch to CS2).
* **Pass:** CS2 suggestions are CS2 settings, cite the VALORANT preference, do not include *Mouse Sensitivity* or any
  VALORANT label, and CS2 values remain unchanged until applied. [e2e: *new CS2 player with VALORANT history*]

## 7. Condition parity and disabling adaptation
* Same scenario; open the same tab in A and in B.
* **Pass:** identical rows and order. In B, **Study controls → Adaptation off** removes *Relevant now* but keeps the menu,
  chat on request, pins and locks. [e2e: *identical canonical rows in both conditions*; vitest: parity]

## 8. Failure paths
* Stop Ollama (or set a wrong `OLLAMA_MODEL`), ask a goal.
* **Pass:** status shows *Model unavailable*; the answer is labelled *Offline fallback — rule-based, not AI-generated*
  with the reason; no state is corrupted. Cancel a running request → “Request cancelled. Nothing was changed.”
  [pytest: timeout, malformed output, cancel, single-flight]
