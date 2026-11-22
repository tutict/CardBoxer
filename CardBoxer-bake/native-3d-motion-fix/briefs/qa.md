# Task: native animation rendering / live QA tooling

Read ../contracts.md first. Work only in this task folder and own
project/tests/native_motion_capture.gd, native_live_check.gd, plus tools/reports.
Do not edit production scripts, authored JSON, or other agents' tests.

First export current actual skeleton metadata for BOTH cached GLB models via a
read-only Godot headless probe (real file log, never NUL): local/global rest,
parents, scales, endpoint positions, model/skeleton transforms. Save
reports/rig-rest.json and send path to root/motion author. This is independent
of production modifications and is needed for native local-axis authoring.

Prepare capture tooling that samples the new NativeMotion public interface into
Fighter3DLayer.apply_visual. Both roles at default cameras, stance/jab/cross/sweep
first, then all 15 + idle/walk/ko. Screenshot after frame_post_draw. Capture a
continuous frame sequence and key contact/overshoot frames, not just static peaks.
Rendering requires a real Windows GL Compatibility renderer; dummy headless frames
are empty. PowerShell Start-Process uses -WindowStyle Hidden. Use real absolute
log/capture paths, clean up only your launched process if it hangs. Never kill all Godot.

In parallel prepare real-state-machine live check/capture harness: taikou and
realtime, fixed input/deck, BOTH player and enemy, wins/draws/block/dodge/combo/super,
wave later collision/new attacker action, facing swap, fatal strike and reset.
No direct application of sampled poses may count as live evidence. Test scenarios
can set initial hands/hp/AI/input in the harness but production tick/play_card/apply_hit
must drive the actual sample. Stop physics after round over, compare gameplay
traces against fixed-input baseline and check same-version 3D toggle invariance.

Geometry QA: final poses on current real GLBs including native guard, both roles,
all phase keys/extrema/transitions. Skeleton math tests don't prove skin quality.
Observe shoulder/elbow/hip/knee seams, cloth distortion, foot support and clipping.
Legacy P5 player-only edge metric excludes stance bias; cannot certify new poses.
Save preview boards/GIF (bundled CPython has Pillow/numpy). Tests/report honest;
don't claim unobserved scenes or successful 3D from dummy-renderer images.

Author/root production files will be written concurrently, so fail gracefully
while NativeMotion/apply_visual are not ready and notify root of dependencies.
Keep tooling useful for repeating QA after adjustments. Report in reports/qa-report.md.
No git commits, no editing/installing actual sibling game, no subagents.
