# Native 3D combat code review

Review date: 2026-11-20. Scope: isolated `project/` implementation against `baseline/`, using `reports/review.patch`, `plan.md`, and `contracts.md`. This is a manual production-code review, not a CodeRabbit result. No production sources were edited, no software was installed, and the existing passing suites were not rerun.

## Findings

### [P2] Preserve signed travel direction when sampling the walk cycle

Primary location: `project/scripts/battle_presentation.gd:200-202`. Related bridge: `project/scripts/fighter.gd:192-193`, `342-343`.

The native walk frame depends only on a phase accumulated from **absolute** distance and on the fighter's facing. The snapshot drops the movement sign, so walking toward the opponent and walking away while facing the opponent produce exactly the same pose sequence. Rotating the model for facing cannot correct this: the facing is the same in both cases. The authored forward stride therefore continues advancing forward during a retreat, reversing the relationship between foot motion and body travel. The legacy renderer explicitly accounts for this distinction at `fighter.gd:941`.

Directed production-code probe: after `reset_for_round(430, 1)`, `tick(0.05, 1.0, true)` and `tick(0.05, -1.0, true)` displaced the two fighters by `+10.75/-10.75` pixels but produced identical presentation snapshots and identical native walk poses. This verifies the lost direction; the precise visual amount of foot sliding was not measured in this review.

Expose signed travel relative to facing in the read-only snapshot and use it to select/reverse an appropriate gait, keeping the fighter's gameplay position, speed, collision, and facing rules intact. Check retreating movement for both roles and both facings.

### [P2] Implement the approved 0.06-second normal pose transitions

Primary location: `project/scripts/fighter_3d_layer.gd:325`. Related selection: `project/scripts/battle_presentation.gd:185-187`, `214-216`.

`apply_visual()` writes each selected pose directly to the skeleton. There is no transition clock or cross-clip blend in the layer or presentation controller. `_blend_stance()` only scales the walk pose by its walk weight; it does not blend an outgoing idle/walk pose into a new action. Thus a normal action replaces an arbitrary outgoing pose with the authored card's stance endpoint in one render frame. Matching all card endpoints to stance avoids some transitions but does not cover idle breathing or an interrupted walking stride. This omits the plan's explicit default: “0.06s normal blends, immediate hit/contact/KO impulse.”

Directed probe: after advancing native idle by `0.15` seconds, starting `jab` immediately selected the exact stance rotations, while those rotations differed from the outgoing idle pose. Source inspection confirms the driver applies that replacement without blending.

Add a visual transition clock for normal clip changes and blend from the previously displayed pose over `0.06` seconds. Preserve immediate hit/block, contact-latch, and terminal KO priorities; freeze the transition with pause/hitstop and clear it on reset. Keep snapshot sampling free of gameplay mutations.

## Coverage and conclusions

No P0/P1 issue was found in the inspected event ordering, terminal handling, or native quaternion composition. The two P2 findings should be addressed before treating the full approved presentation scope as complete.

- All six production script hashes and their two new UID files matched the reviewed change manifest when checked. The patch's script changes were read against the actual source. Model bytes and their separate skin-only preservation claims were not independently re-audited here.
- `NativeMotion` checks required roles/clips, split compatibility, authored contact frames, key ordering/coverage, finite vectors, unit quaternions, guard endpoints, and looping endpoints before making the library available. Sampling clamps phase endpoints and uses shortest-path normalized slerp.
- `RigDriver.apply_pose()` validates the complete pose before bone writes, applies `q_rest * q_delta`, restores local rest translations/scales, and adds one hips root offset. It does not write the neutral import bone. Native layer application skips the old stance bias and composes model-facing rotation from the imported transform.
- Fighter snapshots construct scalar read-only data and do not call hit settlement, RNG, or movement. Action IDs advance on real/visual actions. Visual spark, text, and shake randomness uses a separate RNG.
- Realtime projectile release and collision have distinct source kinds and preserve the projectile's original action ID. Later projectile impacts do not create an attacker contact latch. Fatal late projectiles capture the winner's current action before freeze, allowing that current clip and the victim KO to finish.
- Taikou settles rules immediately and defers its queued impact presentation until `0.48` seconds. The controller clamps the crossing to contact, emits the queue once, holds `0.24` seconds, and preserves overshoot. Its exchange survives the arena's terminal freeze. Terminal KO owns a clock that can finish despite stopped fighter clocks.
- Pause stops arena/controller visual advancement. Round reset clears terminal tracks, impact queues, IDs/latches, saved visuals, hitstop, and slow motion. Existing duplicate guards key realtime impacts by round/actor/target/action/source and exchanges by round/actor/action/winner.
- The arena enables 3D overrides only after both layers initialize; native-data load failure leaves the already-created 2D fighters active. Missing/corrupt legacy `motion_input*.json` and arbitrary incompatible GLB layouts were inspected for fallback structure but were not fault-injected in this review.

## Verification limits

The existing native data/rig, controller, integration, and live legacy suites were reported passing by the task owner; this review does not claim to have rerun them. Only `reports/code-review-probe.gd` was run through Godot 4.5 headless to test the two hypotheses above. It exited successfully; its log is `reports/code-review-probe.log`. The known Windows root-certificate diagnostic was present.

Headless sampling cannot certify deformation, mesh clipping, final sole contact, the camera frame, or exact impact-effect placement. Those remain with the active Compatibility-renderer visual QA. In particular, generic hit spark/ring/text origin still uses logical `victim.position` (`arena.gd:1232`), while rhythm sparks include `visual_shift` (`arena.gd:1467`); inspect their composition in the contact captures before drawing a visual conclusion.
