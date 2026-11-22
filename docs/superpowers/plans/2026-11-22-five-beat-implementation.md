# Five-Beat Tactical Combat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this approved inline execution. Steps use checkbox syntax for tracking.

**Goal:** Make five-beat planning reward distinct attacks, timed recovery, conditional combos and readable public-information forecasts.

**Architecture:** Retain the pure GDScript resolver and finite match controller. Tactical definitions/effects own data; immutable events drive both simulation and existing 3D playback. A pure forecast module runs on an immutable background job and never sees the actual concealed plan.

**Tech Stack:** Godot 4.5, GDScript, WorkerThreadPool, existing native 3D rigs, Python verification runner.

**Spec:** `docs/superpowers/specs/2026-11-22-five-beat-design.md` (approved by the user).

## Global Constraints

- Current `CardBoxer/` project, keep pending English path migration and 3D assets; execute in place as approved, no commits/push/branch changes.
- HAND=8, HAND_MAX=10, PLAY=5, ENEMY_HIDDEN=2, DISCARD_MAX=3, 36 physical cards, three talents, HP=100, six exchanges, three rounds.
- Integer timing, pure state snapshots, exactly-once contacts and stable enemy commitment.
- Keep current 1600x900 HUD, 54px plan slots, sparse high-contrast text and low-saturation colors.
- All numeric values and frozen combo rules come from the spec table.

## Review Focus

- A faster attack before armor startup must punish; damage talents must not inflate interruption power.
- Same-frame movement and dual contacts must remain side-neutral and cannot be reversed by later events.
- End-of-exchange recovery can survive planning while defenses and combo chains cannot.
- Rapid selection edits/restart during a forecast must never apply a stale result or block input.
- A drag cancelled outside the plan row must leave the plan intact; an ordinary click must still cancel one card.

### Task 1: Tactical timing, defense and conditional combos

**Files:** Modify `CardBoxer/scripts/tactical_defs.gd`, `tactical_effects.gd`, `tactical_rules.gd`; add `CardBoxer/tests/tactical_timing_check.gd`; adapt superseded assertions in `tactical_rules_check.gd`.

**Interfaces:** Preserve `resolve_exchange(Array, Array, Dictionary) -> Dictionary`. Add catalog recovery/range/impact/stun-guard/combo fields; state `ready_delay`, `recovery`, `combo`; immutable action wait/start/ready-at/combo data and beat handoff/common recovery. Keep `Effects.apply_ready` generic and old custom effect tests usable.

- [x] Write behavior scenarios for light/strong interruptions, punish startup timing, short/long recovery windows, time-limited defense/feints, range/chase, block draw once, chains/budget/trades/endings, source purity and role symmetry.
- [x] Run `godot --headless --path CardBoxer --script res://tests/tactical_timing_check.gd`; expect named FAIL assertions against the old resolver.
- [x] Implement the catalog table, data-driven effects and integer resolver, including frozen eligibility and next-beat recovery subtraction.
- [x] Run new timing check and adapted existing rule check; expect all assertions pass and exit 0. No old zero-startup assertions remain.

### Task 2: Match lifecycle, reorder and recovery playback

**Files:** Modify `CardBoxer/scripts/tactical_match.gd`, `tactical_presenter.gd`; add `CardBoxer/tests/tactical_flow_check.gd`; adapt tactical match/planning/integration/contact fixtures only where rules intentionally changed.

**Interfaces:** Consume Task 1 beat handoff/common recovery and action wait/recovery metadata. Produce `move_selected(from:int,to:int)->bool`; preserve signals/tick/visual_time and finite-card lifecycle.

- [x] Write failing scenarios for reorder conservation/visibility, fifth-beat delay versus new-round reset, and playback carrying recovery without replaying it. Keep large-delta/pause/restart/KO checks.
- [x] Run flow check; expect missing reorder/recovery schedule failures.
- [x] Implement reorder validation, event-based playback duration and carry poses, without advancing combat time during planning.
- [x] Run flow and existing tactical match/planning/integration/contact checks; expect all pass. Verify 30/60/120FPS results match.

### Task 3: Fair forecasting and bounded AI

**Files:** Add `CardBoxer/scripts/tactical_forecast.gd`, `CardBoxer/tests/tactical_forecast_check.gd`, `CardBoxer/tests/tactical_strategy_check.gd`; modify match forecast lifecycle and `CardBoxer/scripts/tactical_ai.gd`.

**Interfaces:** `forecast_plan(Array,Array,Dictionary)->Dictionary` returns only public per-beat aggregates. Match exposes current forecast/status and manages one immutable WorkerThreadPool job with generation/key checks. AI keeps public-context/physical-index interfaces.

- [x] Write failing forecast privacy/valid fillings/skipped KO/determinism/stale-restart cases and tactical AI legality/eight-style coverage/timing-aware choice/performance cases.
- [x] Run checks; expect absent forecast module/job and old-style AI failures.
- [x] Implement <=324 legal fillings, compact aggregates, latest pending task/cache and 8x3 full AI candidates with spec scoring. No private plan/hand reaches forecast or opponent AI.
- [x] Run checks and ten-card performance cases; expect AI P95 <=500ms and forecast P95 <=1s, legal/stable choices and no stale result.

### Task 4: Compact HUD, drag integration and full verification

**Files:** Modify `CardBoxer/scripts/tactical_hud.gd`, tactical input section of `arena.gd`, `CardBoxer/tests/tactical_ui_check.gd`, `tactical_capture.gd`, `CardBoxer/tools/verify_tactical.py`, `CardBoxer/README.md`.

**Interfaces:** Consume catalog roles/recovery, match forecast/status/reorder and immutable events. Add HUD mouse-event handling; ordinary click paths and existing keyboard controls stay supported.

- [x] Write failing UI behavior assertions for drag vs click/outside cancellation, roles/hover recovery and masked forecast labels; run the existing UI check and watch failures.
- [x] Implement sparse marks/stat lines/hover explanations, one forecast label per slot, waiting/combo status, drag routing and versioned redraw key.
- [x] Add new checks to the verification runner; update README with actual rules and controls.
- [ ] Run the full suite (21 existing scripts plus new checks), actual 3D GPU captures and native interaction QA, then one fresh whole-change review against the saved source baseline/spec.
- [x] Fix important reviewed regressions with RED→GREEN tests, rerun affected/full validation as justified, and deliver the working project with checked evidence.

The combined QA step remains partial only for native desktop drag/play automation: automatic approval review could not process its image and rejected the next input and screenshot. Controller/UI drag events, GPU rendering, independent source reviews and the full26-script suite passed. The user's gameplay complaint does not confirm their completed card order or drag result.

### Task 5: Explain missed and interrupted actions after play feedback

**Files:** Modify tactical definitions/rules/match/HUD, add `CardBoxer/tests/tactical_feedback_check.gd`, register it in the verification runner, extend the GPU capture fixtures and README.

**Reason:** The user reports not landing attacks and repeatedly taking damage. Seed 2026 resolves normal hits correctly, but the HUD hides range in tooltips, suppresses zero-damage outcomes and gives no result for cancelled attacks. Source attack logs describe dodges as a success without naming the defender.

**Interfaces:** Contact events add actual `frame` and `distance` metadata. `Match.feedback_for(role, index) -> Dictionary` returns only already-executed action feedback (`kind`, `label`, `reason`, `damage`, `parts`); `last_exchange_summary() -> String` preserves a compact completed-exchange recap during the next planning phase. Defs provides the shared range label; HUD shows range on hand/plan faces and uses existing side panels for contact explanations.

- [x] Add real controller/HUD regressions for no premature outcomes, wrong-distance misses, cancelled startup, successful versus failed timed defense, source/defender wording, completed-exchange recap and restart reset. Run the new check and confirm named failures.
- [x] Record feedback at actual scheduled contact groups, preserve the preceding completed exchange, and display the card's reach plus short reasons within the current HUD dimensions. Keep all approved combat numbers and rules.
- [x] Verify exact contact-distance metadata before pushback, complete the planned 30/60/120 FPS comparison, run the full suite and render the affected feedback states.
- [x] Review the scoped follow-up, address material findings with regression tests and report the observed limits of the user's unsupplied card sequence and native desktop approval failure.
