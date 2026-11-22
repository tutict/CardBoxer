# Card Boxer Tactical Combat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the revised turn-based fighting/card system with one five-card plan, three visible/two hidden enemy cards, a maximized readable interface, extensible effects, and working 2D/3D play.

**Architecture:** Isolated copy of the current game in project/. Pure tactical_defs/tactical_rules feed a tactical_match state machine and tactical_ai. A presentation adapter and TacticalHUD integrate with the existing Arena and native assets; legacy modes retain their existing rule paths.

**Tech Stack:** Godot 4.5, GDScript, GL Compatibility; existing native assets only.

**Spec:** spec.md (approved user plan).

## Global Constraints

- Latest user revision in spec.md overrides the three-beat/discard-stage entries below. Continue native execution without another approval prompt.
- Tactical planning: 5 ordered cards from 8–10; enemy locks first and exposes exactly 3 cards with 2 random masks. Three Joker slots remain independent.
- Optional per-card swaps, at most 3 per exchange; player edits never alter enemy commitment or visibility.
- Tactical canvas 1600×900, default maximized; preserve the existing authored stage through visual scaling.

### Revision Task A: Rules, commitment and optional swaps

**Files:** scripts/tactical_defs.gd, tactical_effects.gd, tactical_rules.gd, tactical_ai.gd, tactical_match.gd; tests/tactical_planning_check.gd and existing tactical checks.

**Interfaces:** Defs.evaluate(plan, action_count=PLAY); context.action_count; Effects.apply_ready/card_modifiers/joker_modifiers/contact; Match.enemy_preview, swaps_used, swap_card(index). AI keeps bounded candidates for configurable action counts.

- [x] Write/run five-action, partial-plan rejection, fifth-beat opening, exact masking, stable commitment, bounded optional swaps and generic-effect scenarios RED.
- [x] Implement five-card patterns and data-driven effect execution, bounded AI, pre-planning enemy lock/mask, direct optional swaps.
- [x] Run pure rules, planning and match checks GREEN; preserve explicit three-action combat characterization fixtures.

### Revision Task B: Single-page large HUD

**Files:** scripts/tactical_hud.gd, scripts/arena.gd, project.godot, launchers; tests/tactical_ui_check.gd, tactical_integration_check.gd, tactical_capture.gd, tactical_contact_check.gd.

**Interfaces:** HUD.plan_rect(role,index), plan_card(role,index), swap_card_rect(index); shared mouse and Shift+number actions; independent 1600×900 HUD with proportional legacy stage.

- [x] Update UI expectations for immediate planning and five visible slots; run RED.
- [x] Reflow header/plans/hand/controls, show real enemy cards and masked details, enable optional swap buttons and maximize startup.
- [x] Run integration/UI/contact checks GREEN; inspect real 2D/3D captures and verify both input paths.

### Revision Task C: Final verification and installation

- [x] Run the entire tactical/legacy suite and capture final readable screens.
- [x] Obtain one fresh review of the revised feature; fix important findings with regression checks.
- [x] Rebuild hash-guarded release, install the verified file set in the original game, verify installed launch paths, and leave the updated maximized game open.

- 8 base hand, 10 maximum, 3 selected in order, 3 maximum discards; 18 cards x2 per deck.
- Eight unique Jokers, offer six and choose three in order; six turns per round, at most three rounds.
- Logic is deterministic and independent of rendering; hidden player input is inaccessible to AI.
- Work only on this feature's copy until validation, then transfer this feature's file set to the original with baseline checks.
- Do not stage unrelated untracked historical assets. This workspace has no HEAD, so isolated-copy hashes and patches replace unavailable Git revision ranges.

## Review Focus

- Reordering duplicate card types must not spend one hand slot twice.
- Last-beat openings/buffs survive into the next exchange but never into another round.
- Failed/blocked attacks must not manufacture successful-hit triggers.
- Large delta, pause, or restart must not duplicate a contact or skip a double KO.
- A 10-card hand and six-card loadout must fit the logical 1600x900 tactical canvas and have equivalent keyboard/mouse actions.

### Task 1: Catalog and pure combat

**Files:** scripts/tactical_defs.gd, scripts/tactical_rules.gd; tests/tactical_rules_check.gd.

**Interfaces:** card(id), evaluate(plan), default_context(), resolve_exchange(player_plan, enemy_plan, context) -> events/next_state/error. Beat events contain atomic contact groups, action metadata, state snapshots, damage parts and passive triggers.

- [x] Write rules/catalog scenarios and run them RED.
- [x] Implement exact spec values, staged action timing, atomic contacts, distance, openings and ordered passives.
- [x] Run rules suite GREEN, including swapped Joker arithmetic and double KO.

### Task 2: Deck, fair AI and match flow

**Files:** scripts/tactical_ai.gd, scripts/tactical_match.gd; tests/tactical_match_check.gd.

**Interfaces:** AI choose_plan(hand, public_context, role), choose_discards(hand, public_context, role). Match exposes phase/state/hand/offers/selected/enemy_hint, toggle/undo/confirm/tick, and contact/beat/round signals. AI receives no hidden opponent hand or pending plan.

- [x] Write seeded deck conservation, draft/order, flow, cap, hidden-input and turn/round-limit scenarios; run RED.
- [x] Implement finite draw/discard/recycle, commit-before-preview AI, phase queue and idempotent contact consumption.
- [x] Run rules + match suites GREEN; verify frame-rate independence and pause/restart.

### Task 3: Arena and 2D/3D presentation

**Files:** scripts/arena.gd, scripts/fighter.gd, scripts/tactical_presenter.gd; tests/tactical_integration_check.gd.

**Interfaces:** presenter sampling uses rule events and existing native clips; Fighter accepts visual snapshots/impacts without realtime damage. Arena owns a TacticalMatch only for tactical mode and routes input/rendering accordingly.

- [ ] Write default-mode, contact-only HP, visual-only, clip-mapping, interrupted-action and old-mode scenarios; run RED.
- [ ] Integrate default tactical, authoritative snapshots, atomic contact FX and reusable 2D/native clips.
- [ ] Run all tactical suites and explicit taikou/realtime regression suites GREEN.

### Task 4: Playable HUD and controls

**Files:** scripts/tactical_hud.gd, Arena HUD/input bridge; tests/tactical_ui_check.gd.

**Interfaces:** shared hit rectangles for keyboard/mouse; loadout and hand selection order displayed; hover details, opponent hint and damage-source log; redraw signature contains tactical state.

- [ ] Write ten-hand layout, six-offer draft and mouse/keyboard-equivalence scenarios; run RED.
- [ ] Build HUD using existing typography/palette/portraits with three-plan and three-Joker strips.
- [ ] Run suites GREEN and inspect real 2D and 3D keyboard/mouse flows.

### Task 5: Delivery and whole-feature review

**Files:** README.md, launchers, check/capture scripts, release manifest and verified source patch.

- [ ] Run complete scripted match and deterministic scenario captures at varied FPS.
- [ ] Run legacy regressions and inspect actual 2D/3D game screenshots.
- [ ] Fresh-context whole-feature review; reproduce/fix important findings with RED→GREEN checks.
- [ ] Verify original baseline hashes, back up affected originals, install only the validated feature file set, and verify installed launch paths.

- [x] Run the entire tactical/legacy suite and capture final readable screens.
- [x] Obtain one fresh review of the revised feature; fix important findings with regression checks.
- [x] Rebuild hash-guarded release, install the verified file set in the original game, verify installed launch paths, and leave the updated maximized game open.


### Revision Task D: Compact card surfaces

**Files:** scripts/tactical_hud.gd, tests/tactical_ui_check.gd, assets/tactical/hidden_card_back.png, release tooling.

- [x] Add behavior-level checks for concise view models, five compact slots per row, 3 visible/2 masked enemy cards, hand width through ten cards, and hover-only full card text.
- [x] Show all 21 card, planning, match, legacy and native checks passing; capture and inspect the updated 2D and native 3D screens.
- [x] Install the UI and Comfy-generated muted card-back texture in the original project, rebuild Godot's import cache, and verify installed UI and planning checks.
