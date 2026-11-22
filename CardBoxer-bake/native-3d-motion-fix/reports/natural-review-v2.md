# Natural motion V2 — independent code review

Reviewed 2026-11-20 against `versions/v1/`, with `natural-flow-v2.md`, the runtime/authoring reports, current production consumers and focused tests. No production sources, assets, installation or commits were changed. The review produced this report and a report-local transition probe/log.

## Findings

**No actionable functional, resource-retention or performance regression was found in the inspected V2 changes.** This is a code review and focused numerical check; final rendered naturalness remains the root's visual acceptance step.

- `native_motion.gd:184` clamps sampling, preserves exact authored arrays at keys, aligns quaternion hemispheres, and uses neighboring key times for cubic interpolation. Walk/idle borrow cyclic neighbors with the correct period. Root Hermite slopes share each interior key's derivative and bound monotone segments; phase/contact mapping remains unchanged. Current dense data contains explicit phase/contact endpoints and the same card counts/28-frame KO contract.
- `native_motion.gd:265` caches only rest transforms, parent names, weighted bind transforms and packed boot vertices. Both temporary imported models are freed; no Node, Skeleton3D, MeshInstance3D or Skin reference is retained in the cache. `load_data()` clears both library and support cache. Setup prewarms before battle; existing saved real-render evidence measures the resulting frame cost rather than assuming it.
- `native_motion.gd:341` deep-copies the pose and changes only root Y by the reference/overlay support difference. It does not mutate either input or touch root X/Z. `battle_presentation.gd:263` derives travel from the existing calibrated contact contribution, holds it until .56s, and returns it to zero at 1.12s. Signed gait samples approach/retreat separately and reaches zero weight at contact/guard. Pause/hold return before visual clocks advance, and repeated sampling recomputes the same support adjustment without accumulating it.
- Gameplay positions, damage, phase clocks and event settlement remain in their existing Fighter/Arena paths. The controller's additions only change displayed pose/root Y and canvas shift. Terminal/contact priorities still bypass ordinary transitions; reset clears outgoing poses/transitions and event clocks.
- `update_verified_changes.py:13` derives expected main hashes from the installed receipt, supplements unchanged files from the original baseline, checks target identity/path containment and refuses both external main edits and stale candidate hashes. The apply loop rechecks each main file, preserves a versioned backup, verifies the temporary copy, replaces it atomically and records completed copies. Existing recovery points and unrelated temporary files are refused. The original installer must not be reapplied over V1.
- `install_verified_changes.py:61` now expects the actual `NATIVE MOTION CHECK: PASS` marker. Other generic CHECK markers also require process exit 0 and absence of GDScript parse/runtime failures; their test scripts exit 1 on assertion failure. The known certificate-store diagnostic is not mistaken for a motion failure.

## Focused fresh verification

The exhaustive existing support test intentionally clears ordinary transitions, so I checked the final displayed walk-to-card blend separately. `natural-review-v2-probe.gd` sampled both roles, eight outgoing walk phases, all 12 cards and six 10ms transition steps: **1,152 samples**, maximum absolute sole offset **0.01233855m**, inside the specified 0.020m tolerance. Worst case was foe walk phase .25 into sweep at .05s. Godot exited 0 with only the known certificate-store diagnostic. No full suites were rerun.

A read-only call to `prepare_update()` refused the current manifest with **`Candidate manifest is stale: data/combat_motion_3d.json`**. The manifest still identifies V1, so regenerate it from frozen V2 before installation. This is the expected stale-source guard, not an update failure or a main edit.

Inspected saved evidence, not freshly rerun by this reviewer: natural runtime 1031/1031; native geometry 2,966 samples/max support .002570987m; old controller 44/44, transitions 51/51 and spacing 70/70; both live modes 14/14; actual Compatibility render 60.0024 FPS, 420 intervals across 6.999719s. The focused probe does not replace whole-cycle visual review.

## Reviewed hashes

| File | SHA-256 |
|---|---|
| `project/scripts/native_motion.gd` | `cbc9a3eee51c4d5e55f46365ef636c87bd3b0fd48f21d1a5f964d4a26164515f` |
| `project/scripts/battle_presentation.gd` | `2e8edb3f07ebdb99a78c4c1906b2570185b129e4b9af20d590d28ade81243171` |
| `project/data/combat_motion_3d.json` | `083c84e3e24bdb4bea6d3e4b92855322caea97d675cae19a06df36acefd5a703` |
| `tools/update_verified_changes.py` | `7bcca4eef3f50d50ff366d5033a524d69263709ca2cc896ba7d174cb057818a0` |
| `tools/install_verified_changes.py` | `2846ce12c45d1498e6b573df90fd46d2d150edf2a8d09d8f4439848b9872e164` |
