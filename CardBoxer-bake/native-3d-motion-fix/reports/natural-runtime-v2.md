# Natural runtime flow v2

Implemented only candidate `project/scripts/native_motion.gd`, `battle_presentation.gd`, the explicitly authorized old controller assertions, and new `project/tests/natural_runtime_check.gd`/`natural_runtime_benchmark.gd`. No sibling production checkout, rules, phase counts, GLBs, layer, arena or fighter code was edited by runtime flow.

## Sampling and travel

Native quaternion interpolation now uses Godot's time-aware spherical cubic interpolation with shortest-path hemisphere alignment and normalization. Uneven key intervals share velocity through intermediate poses. Sampling an authored key copies its exact rotation/root arrays, including contact and phase endpoints. Walk/idle borrow cyclic neighbors at their loop seams. Root uses monotone time-aware Hermite slopes: nonzero velocity through monotone intermediate keys, zero at extrema, and no root overshoot between samples. The author agreed to half-frame target/IK/grounded breakdowns with the same version1 pose schema.

The taikou actor's former triangular110px pulse and smoothstep extra approach now form one quintic approach/return curve with the **same exact .48s calibrated contact contribution**. After contact the hand's native recovery progresses while travel remains at contact space through .56s; return settles at1.12s. No clocks, cues, hold logic, phase mapping, KO priority or gameplay positions changed.

Actual signed visual distance drives a120px gait cycle; return samples the cycle in reverse. Smoothly saturated visual speed controls a restrained additive walk delta on thighs/shins. Zero travel speed restores the authored pose exactly at contact/guard. Upper-body rotations remain authored throughout. The additive gait's pelvis Y compensation preserves the reference pose's lowest **actual weighted imported boot vertex**, using cached read-only Skeleton3D rest and Skin bind data. Root X/Z remains authored. This adds no bones, mesh changes or gameplay movement.

Support cache now groups boot vertices by identical Skin bind weights, combines each group's weighted affine matrix, and transforms its original `PackedVector3Array` through Godot's native batch operation. Every original classified boot vertex remains measured; no conservative proxy, extrema selection or hull approximation was needed. `Presentation.setup()` prepares both role caches before battle so the first dash does not pay the import/packing cost.

## Red/green evidence

- `natural-runtime-red.log`:198/209. Expected failures show intermediate quaternion/root stopping, a non-exact root key, immediate torso retreat, missing return gait and missing signed travel.
- `natural-runtime-interpolation.log`:203/209 after quaternion/root interpolation; remaining six failures were forward/return behavior.
- `natural-runtime-green.log`:209/209 after travel and support implementation.
- `natural-runtime-final.log`:947/947 after exhaustive full-cycle imported-sole checks and smooth gait-strength saturation.
- `natural-runtime-final-natural_runtime_check.log`:1031/1031 with an independently posed in-tree Skeleton3D and original full imported Skin/mesh measurement. Packed support agrees with that independent path within1 micrometer. The initial independent test measured an out-of-tree skeleton that did not update its global bone poses; adding it to the live SceneTree corrected the test setup. No production workaround was introduced.

The1031 checks cover uneven-time quaternion/root velocity continuity, nonzero interior velocity, exact authored samples, unit quaternions, both roles' approach/return direction, exact .48s calibrated pose/shift, contact hold, paused approach, delayed retreat, exact1.12s guard/zero shift,41 full-cycle support samples per role and unchanged upper-body rotations. The foot overlay preserves authored support within10 micrometers. Independent full-mesh maximum absolute support error was0.000635m player and0.000995m foe.

Fresh regression results:

| Test | Result | Log |
|---|---:|---|
| battle_presentation_check |44/44|natural-runtime-final-battle_presentation_check.log|
| native_motion_check |PASS0,2966 samples, max support0.002571m|natural-runtime-final-native_motion_check.log|
| battle_transition_check, native3D |51/51|natural-runtime-final-battle_transition_check.log|
| battle_contact_spacing_check, native3D |70/70, six gaps0px|natural-runtime-final-battle_contact_spacing_check.log|
| battle_integration_check, native taikou |14/14|natural-runtime-final-battle_integration_check.log|
| battle_integration_check, native realtime |14/14|natural-runtime-final-battle_integration_check-realtime.log|
| taikou_flow_check,3D off |51/51|natural-runtime-final-taikou_flow_check.log|
| battle_rhythm_check,3D off |62/62|natural-runtime-final-battle_rhythm_check.log|

The root owner explicitly authorized revising the old dash assertions to require exact upper/hand rotations, unchanged root X/Z, and measured actual sole support. Controller now passes44/44. Its exact full authored contact pose remains immutable. The author's final role-specific guard fixes pass the full native geometry suite above.

## Measured CPU cost and real renderer

`natural_runtime_benchmark.gd` samples each role over480 frames at the60Hz presentation timeline. Two independent controllers then animate both native actors' complete approach/return cycles simultaneously in the actual Windows OpenGL Compatibility renderer at1280x720. The production Arena/layers are displayed, while gameplay is held for a repeatable motion stress case. This is a heavier sampler case than ordinary taikou's single moving attacker. No `--fixed-fps` simulation option is used; the measured presentation cap is60FPS with vsync disabled.

| Measurement | Player | Foe |
|---|---:|---:|
| Original warm sample mean |4.56ms|4.65ms|
| Optimized CPU sample mean |1.193ms|1.227ms|
| Optimized CPU sample p95 |1.392ms|1.477ms|
| Optimized `preserve_support` mean |1.136ms|1.172ms|
| Sample during actual rendering, mean |1.551ms|1.440ms|
| Sample during actual rendering, p95 |1.920ms|1.672ms|

Final actual renderer result: **60.0024FPS**,420 measured frame intervals across6.999719 seconds after a1-second warmup. Mean frame interval16.666ms, p95 16.684ms, maximum17.063ms. Logs: `natural-runtime-render-optimized.log`, `natural-runtime-render-optimized-stdout.log` and stderr counterpart. Original real renderer also met60FPS, but consumed about8.55ms combined sampler time; optimized combined sampler mean is about2.99ms, leaving substantially more CPU margin.

Both caches take1.859 seconds once during setup on this host; a second setup using the same library takes7 microseconds. The first post-setup pose samples take1.645ms/1.486ms. Before prewarming, the first mid-fight cache miss had cost0.75-1.0 seconds; that allocation now occurs before the battle starts. There are no changed gameplay timers or added action waits.

The host's usual root-certificate-store warning is retained in logs. An initial invocation of old pure flow/rhythm tests incorrectly enabled native3D before those tests enter their SceneTree; it produced camera/tree diagnostic errors despite passing assertions. Both were rerun in their normal3D-off configuration above; those clean runs have only the known certificate diagnostic. No production workaround was introduced for test setup.

## Remaining visual judgment

Headless evidence confirms motion continuity, support, exact contact and ordering. Root-owned whole-body normal-speed and slow-motion renders still need to judge glove overlap, step frequency/stride, backward shuffle readability, hand-before-torso recovery and any transient articulation spikes. Gait is deliberately restrained; imported models still have their existing rigid hand shapes. No claim of final rendered naturalness is made by these checks alone.
