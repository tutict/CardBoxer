# Five-beat tactical combat (approved 2026-11-22)

User approved the proposed plan and requested implementation. The target is the current `CardBoxer/` Godot project, preserving the pending English path migration, existing 3D assets and tactical HUD dimensions. Implement in place; retain the user's uncommitted work. No branch, commit, push or publishing is part of this request.

## Combat contract

Keep 8-card hands (maximum 10), one ordered 5-card commitment, three optional swaps, enemy commitment before planning, three actual visible enemy cards plus two randomly hidden cards, 36 physical cards (two of each ID), six-offer/three-talent draft, 100 HP, six exchanges per round and up to three rounds/best of three.

`resolve_exchange(player_plan, enemy_plan, context) -> {events, next_state, patterns}` remains pure. The tactical catalog owns all tactical parameters, independent of realtime values. Distances are 0=close, 1=middle, 2=far. Values below are project-specific defaults based on the previously verified BattleCON/Yomi design references, not copied rulebook statistics.

| ID | startup/damage | range | recovery/whiff | hitstun/blockstun | impact/stun guard | combo |
|---|---|---|---|---|---|---|
| jab | 4/4 | 0..1 | 6/8 | 9/6 | 2/0 | starter |
| cross | 6/6 | 0..1 | 8/11 | 10/5 | 3/0 | starter_linker |
| uppercut | 8/10 | 0 | 13/19 | 17/5 | 6/0 | ender |
| sweep | 8/6 | 1 | 10/14 | 14/5 | 4/3 | starter |
| wave | 10/9 | 1..2 | 14/20 | 10/7 | 3/0 | standalone |
| throw | 5/8 | 0 | 11/16 | 12/0 | 4/0 | standalone |
| pursuit | 6/5 | 0..1 | 7/11 | 9/4 | 3/0 | linker |
| guard_break | 9/8 | 0..1 | 12/17 | 12/0 | 5/0 | ender |
| delayed_heavy | 12/9 | 0..1 | 13/18 | 15/8 | 5/0 | standalone |
| armored_heavy | 10/10 | 0..1 | 14/20 | 15/6 | 6/5 | standalone |

Other cards (startup/recovery): rush 4/4 moves one closer; backstep 3/5 moves one farther; guard 2/0 blocks through this beat, reduces damage 80%, first successful block per exchange grants one next-hand draw; sidestep 2/6 dodges during [contact, contact+9); parry 2/8 has the same window for non-throw melee, successful recovery becomes 4 and the attacker incurs whiff recovery+4; feint 4/5 at distance 0..1 baits an actually active defense and floors opponent ready-at at own ready-at+6; focus 10/6 stores +3 for the next committed attack attempt; recover 4/3 reduces its own start-of-beat delay by four and draws one on completion. Non-attacks have damage/impact/stun guard zero. All defenses expire at the next beat.

Sweep's unblocked hit pushes distance one farther. Cross adds three damage on counter. Throw bypasses block/parry and breaks stun guard but remains dodgeable. Guard break bypasses block. Wave cannot be parried. Delayed heavy has no defense-immunity tags: it catches defenses only when their active window expires.

## Integer timing and recovery

Each beat pairs one action per side. State gains `ready_delay` (0..12), recovery source metadata and combo state. `exposed` is only a derived compatibility indicator, never an input to zero-startup punishment.

Contact frame = delay + max(1, startup - tempo - combo_discount). Frames through delay are waiting; armor is active only in the actual attack startup. Contact within opponent delay (inclusive) is punish (+3); contact into an already-started pending attack is counter (x1.25). These are exclusive. Impact, not multiplied damage, decides interruption against stun guard; throws break it. Same-frame defense/movement resolves before atomic simultaneous attacks.

Ready-at is contact+recovery for a normal action and contact+whiff-recovery for a miss/dodge/parry (parry adds four). Interrupted actions replace their original ready-at with hit-frame+hitstun. Other unarmored hits/block contacts take the later of existing recovery and contact+hitstun/blockstun; successful stun guard takes damage without hitstun. Handoff is the last ACTUALLY EXECUTED contact/action completion, excluding recovery/window-end/cancelled action times. Remaining recovery is max(0, ready-at-handoff); subtract both sides' common minimum, then clamp each difference to 12 for the next beat. Fifth-beat delay survives the exchange boundary, new rounds clear it. Charges retain their existing cross-exchange semantics.

Playback reaches handoff plus common recovery, not both actors' full recovery; residual recovery is displayed during the next beat's waiting period. No repeated wait. Immutable events expose contact, wait, recovery and combo reasons. Contact IDs remain exactly-once under pause, restart, large delta and KO.

## Conditional combos

Four points per exchange; starter/linker cost one, ender two. Actual starter hits open a chain. Previous unblocked hit with no incoming unblocked damage is required to link. Same-frame trades never open/continue a chain. Enders close it. Defense/movement/setup/standalone attacks, failed contact or exhausted budget close it. New starters can open a fresh chain without receiving a linker discount. No chain crosses an exchange boundary.

Spent points remain spent when a chain breaks or reopens; four is the total exchange budget, not a fresh allowance for each chain. Returned next-exchange state clears both open-chain and spent-budget indicators.

At beat preparation freeze combo eligibility, point spending and startup discount two using previous state and current range (pursuit projects its own one-step movement). Then determine contact frame. Pursuit enhancement is an eligible link OR a reachable punish at that frame with its projected move; it moves one closer and gains three. An opponent's movement before/same-frame contact may still cause a miss; never reschedule or retroactively undo contact. Eligible failed attempts do not refund points. Ineligible attacks remain normal attacks, with no combo cost/discount. Preserve all patterns/eight talents and ordered damage math. Pressure and combo discounts stack, startup >=1; neither reduces waiting delay.

## Planning, forecasting and AI

`move_selected(from, to)` reorders physical selected hand indices, without spending cards/swaps or changing enemy commitment. Drag reorders; ordinary clicks keep cancellation semantics. Keep 54px plan slots and current hand sizes, low saturation and sparse text; detailed range/recovery/role data lives in hover tooltips.

`forecast_plan(player_plan, enemy_preview, public_context)` only uses public input. For complete five-card selections enumerate up to 324 two-mask fillings respecting two copies of an ID. Run the real resolver and aggregate player contact kinds, damage, distance and delay; include KO-skipped beats. Never output hidden IDs/ranks or probabilities. One background task, latest pending immutable snapshot only, discard stale results, bounded cache by public state/selection. One short per-slot risk label; partial plans show roles only.

AI groups: rush; backstep; guard/sidestep/parry; jab/cross/sweep/pursuit; wave; throw/guard_break; uppercut/delayed_heavy/armored_heavy; feint/focus/recover. Eight intermediate beam entries and three full candidates per group (<=24 full simulations); eight templates plus last three public histories. Score net damage, plus effective next-draw difference and .25*(opponent delay-self delay) only when another exchange exists. Enemy input never includes the player's hand or pending selection.

## Acceptance

Cover distinct impact/stun guard, short/long punish windows, timed defenses/feints, range and chase, guard draw once, charges, valid/failed combos/budget/endings, atomic trades/double KO, carry/reset, pure inputs, finite deck/seed/visibility stability, forecast privacy/staleness, and 30/60/120 FPS/pause/restart. Current-machine ten-card scenarios: AI P95 <=500ms, complete forecasts P95 <=1s. Run the existing 21-script regression suite plus new behavior checks and 3D interaction/capture QA. No new cards/assets/economy/cooldown pile/save migration. Baseline before edits: 2045 rule and 113 planning checks passed.
