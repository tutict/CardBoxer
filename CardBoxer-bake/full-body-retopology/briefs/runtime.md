# Progressive hands runtime review brief

Read ../spec.md and ../contracts.md first. Scope is Task 4 of plan.md:
NativeMotion hand_grip sampling, ordinary body pose blends/equality, rendered
morph application, forearm-local open/half/closed socket interpolation, pose-clock
freeze/reset/KO handling and foe-only local canvas gain. Root owns this scope.

At every scalar g, coefficients are:
0..0.5 => Basis 1-2g, half 2g, closed 0;
0.5..1 => Basis 0, half 2(1-g), closed 2g-1.
Exact targets grip_half_f, grip_f, grip_half_b, grip_b are independent by hand.
Invalid finite/range/schema values must fail before body or displayed hand changes.
Original body rotations/root/phase data and gameplay timing/positions/damage stay
unchanged. Hand-only changes invalidate render state. Source canonical skeleton,
asset/profile conversion and final raw input acceptance are dependencies from
Tasks 1-3; final real imported socket/render/performance gates belong to Task 5.

Review current code and real recorded evidence, not completion claims. Check
exact role/hand order, target indices, progressive coefficients, surface-0 boot
behavior, raw-basis leakage, ordinary transitions, paused/hitstop clocks, KO/reset,
late contact/FX and foe shader isolation. Root has a fresh all19/both-role original
body sampler comparison, 151/151 hand behavior tests and genuine initial missing
asset/profile RED. Final asset-dependent checks are still pending author outputs
at this review boundary; state precisely which axis/dependency remains unmet.

Use all four independent review axes: Spec, Standards, Implementation Quality,
Verification & Evidence. All apply. Scope your verdict to this runtime task and
separate final integrated acceptance gaps. Review is read-only; write findings only
to reports/runtime-review.md. Do not modify implementation or create subagents.
