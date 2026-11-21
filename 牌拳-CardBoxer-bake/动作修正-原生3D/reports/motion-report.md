# Native motion authoring and sampler

Status: complete 19-clip native library for both measured roles; ready for visual acceptance by root/QA. Full data, sampler and tests are available in the isolated project. No actual sibling game edits, shared integration/driver edits, mesh edits, subagents or commits.

Final grounding revision after larger orthographic render: the former shin-tail support metric was an incorrect proxy for the soles. Actual CPU skin deformation measured player stance front/rear soles at -0.08734/-0.23161 m and foe at -0.08762/-0.24070 m. The initial actual-mesh regression run failed 152 authored support checks, and final KO visible minima were -0.35228 m player/-0.42438 m foe.

`author_native_grounding.py` now measures original boot vertices with >65% influence from the appropriate shin and rest y<0.24 m: 3,001/2,956 player and 3,204/3,146 foe vertices. Each leg IK target height is iterated against the current GLB's exact weighted sole minimum; a lifting foot keeps its authored clearance. Node hierarchy, inverse bind matrices and unchanged skin weights are reused from the skin agent's read-only CPU helper. All existing root offsets and upper-body/hand orientations remain unchanged; native root offset is still applied once. No foot bone or model edits are added.

The current stance sole minima are within 0.000014 m of floor y=0 on both roles. Final KO whole visible mesh minimum is -0.01057 m player and +0.000006 m foe. KO retains 28 frames/0.45 seconds; an added intermediate collapse key at frame11 corrects a 3.38 cm inter-key support excursion without changing the final dramatic fall angles. `author_native_ground_check.py` checks every authored key in all19 clips, both models and alternate walk support. `project/tests/native_motion_check.gd` now reconstructs actual imported ArrayMesh boot deformation using the real Skin bind poses instead of shin-tail y. All1,502 integer/half-frame poses pass; maximum actual support-sole error across stationary motions, all attacks/reactions, alternate walk, sweep and KO is 0.012953 m. The old tail assertions were retired after the calibrated poses correctly violated them: the ankle/shin-tail must sit above the sole.

Actual-sole results: `reports/motion-actual-sole.json`; fresh engine run: `logs/native-motion-actual-sole.log`. The NumPy authoring dependency now comes from the bundled runtime and existing skin helper; no Python dependency enters the runtime sampler. Root can set the native ground projection to model y=0. Fresh real-render review of this grounding revision remains root/QA-owned.

Update after root's core render review: guard calibration now raises and advances both hands toward chin, with role-specific wrist targets. Player guard hand +Z is now 0.55903/0.49056 m (previous 0.42918/0.32513); foe is 0.62536/0.54779 m (previous 0.49701/0.38539). All card/reaction guard endpoints and idle/walk breathing were regenerated, plus high guard/block and supported attack hands. Jab/cross/sweep authored contact reaches, root/feet and arcade torso ranges remain unchanged. `logs/native-motion-guard-red.log` recorded four intended guard-depth/height failures before calibration; `logs/native-motion-guard.log` passes all 1,502 sampled poses and separated-elbow/chin/depth tests, with unchanged 0.01580134 m maximum support-foot height error. Fresh render acceptance is pending; root owns camera framing, separate skin work owns hair/cloth spikes and seams.

## Owned deliverables

- `project/scripts/native_motion.gd`: all six public methods from contracts.md, explicit `last_error` diagnostics, fractional frame sampling, smoothstep interpolation and normalized quaternion slerp using the shortest hemisphere. Returned arrays are copies and cannot mutate the library. Frames clamp; phase progress 1 returns the phase's final authored frame; absent zero-length active phases remain at the preceding windup boundary.
- `project/data/combat_motion_3d.json`: version 1, Godot +Y up/+Z forward, 13 named local rest-relative quaternions and one skeleton-local root offset per key. Player and foe each contain stance, idle, walk, ko, 12 cards and hit_light/hit_heavy/block.
- `author_native_motion.py`: deterministic authoring using NumPy skin measurement helpers for actual boot-floor calibration. Reads actual exported local/global rest transforms from `reports/rig-rest.json`, exact joint origins and source apose leaf endpoints from each role's own `motion_input*.json`. Card split is parsed from the current `card_data.gd`; card frame count is checked against each source input. It does not read old 2D motion trajectories, old bakers or amplitude-retarget mapping.
- `project/tests/native_motion_check.gd`: runtime data contract, phase timing, closure, true imported-rig FK geometry, all integer/half-frame samples, independent interpolation fixture and invalid-data rejection.

## Pose design

The author solves analytic two-bone IK separately for all four arms and all four legs across the two models. Desired segment directions live in skeleton 3D. Bone orientation preserves the measured rest frame with an independently authored roll; each global solution is converted through its solved parent's orientation and then `q_delta = inverse(q_rest) * q_local`. Imported bone scales/positions, topology, materials, names and hand mesh shapes remain unchanged. The hand shapes therefore remain open on the player and armored fists on the foe.

Guard bends both elbows in front of chest/head. Jab reaches with the front arm; cross reaches with the rear arm and rotates hips/chest; uppercut drops then rises; sweep winds the front leg behind and sideways, crouches, crosses laterally during active, reaches +Z near the ground and continues into overshoot. Wave chambers and extends both palms; throw reaches/grabs before torso rotation and follow-through. Rush/backstep use opposite leaning/footwork, guard lifts both hands, sidestep ducks and shifts sideways, focus chambers low symmetrically, recover rolls/compresses then releases. Idle breathes; walk alternates lifted feet; reaction key 0 is impact, then recoil/overshoot/recovery. KO begins heavy impact and ends down at frame 27. All cards return exactly to the authored guard, idle/walk close their loops.

## Test-first evidence

Actual Godot 4.5 was used with real log files throughout:

1. `logs/native-motion-red.log`: exit 1, intended missing sampler failure before implementation.
2. `logs/native-motion-prototype.log`: exit 0, stance/jab/cross/sweep on both roles available for early rendering.
3. `logs/native-motion-coverage-red.log`: exit 1, 30 intended missing-full-coverage failures before remaining 15 clips per role were authored. Initial real-rig FK directions already passed.
4. `logs/native-motion-full.log`: exit 0, full coverage and actual imported-rig FK checks passed.
5. `logs/native-motion-validation-red.log`: exit 1, five intended invalid-data acceptance failures before strict validation was added.
6. `logs/native-motion-validation.log`: exit 0, full contract and independent interpolation/invalid fixtures passed.
7. `logs/native-motion-range.log`: exit 0, 1,502 integer/half-frame native poses checked, zero failures; maximum support-foot height error 0.01580134 m across stationary/card sweep support samples.

The engine emits its environment warning `Failed to read the root certificate store` after both passing and failing headless checks. No GDScript parse/runtime errors were present in the passing runs.

Actual imported Skeleton3D FK measured front/rear guard hand +Z: player 0.42918/0.32513 m, foe 0.49701/0.38539 m. Jab front contact +Z: player 0.78306 m, foe 0.90378 m. Cross rear contact +Z: player 0.77973 m, foe 0.91803 m. Sweep contact front foot +Z: player 0.79 m, foe 0.67 m. Uppercut rise, dual wave extension and KO down endpoints pass.

Invalid fixtures reject missing required clips, wrong stance duration, non-unit/missing quaternions, nonincreasing keys, wrong root dimensionality, contact drift, missing authored contact key, open card endpoint and open walk loop. A literal antipodal 90-degree quaternion fixture confirms 45-degree midpoint yaw, eased quarter sampling, root interpolation, clamping, missing role/clip diagnostics, NaN rejection and sample-copy isolation.

Repeat from workspace:

```powershell
& 'C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1118-904-0_26.1118.904.0_x64__3k8sg7r9htsxt/dependencies/python/python.exe' '动作修正-原生3D/author_native_motion.py'
& 'C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe' --headless --path '动作修正-原生3D/project' --log-file '../logs/native-motion-range.log' --script res://tests/native_motion_check.gd
& 'C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1118-904-0_26.1118.904.0_x64__3k8sg7r9htsxt/dependencies/python/python.exe' '动作修正-原生3D/author_native_ground_check.py'
```

## Visual evidence and remaining concerns

Author inspected QA's real renderer stance/jab/sweep core boards. They show independent guard, arm extension and crouch/leg movement on both original skins. Guard/jab lower boots touch or cross the viewport edge and player sweep contact boot crosses the right viewport edge; root was notified to assess camera framing. Some thin elongated player hair/cloth strips are visible on sweep. These concerns require root/QA review of all 19 clips, both facings and continuous/live motion before installation. Numeric FK is not claimed as visual quality certification. Root/integration own the complete project regression suite and final gameplay/install verification.
