# Native 3D animation QA tooling

Status: tooling ready; real OpenGL Compatibility rendering succeeded on NVIDIA GeForce RTX 5080 Laptop GPU. Both actual GLBs were captured through the final native library/layer interfaces. Image presence and real-state-machine timing checks passed; final art acceptance remains with root, who is inspecting and adjusting the authored poses. No dummy-renderer picture is counted as skin evidence.

## Observed and verified

- `rig-rest.json` is a read-only export of BOTH actual cached GLB Skeleton3D instances. Each contains all 14 bones, parent indices/names, local/global rest transform, basis columns, quaternion, scale, determinant, exact child joint origins, model/skeleton transforms and all imported Node3D transforms. Godot has no imported bone-tail metadata; leaf endpoints are explicitly marked unavailable.
- `native_motion_capture.gd` and `native_live_check.gd` passed Godot 4.5 parse checks. Python tools passed compilation/execution. The launcher starts only an owned hidden helper, uses real absolute engine/stdout/stderr log paths, flags runtime script errors even when Godot reports exit 0, and terminates only that Process object on timeout.
- Baseline, current 3D-off and current 3D-on fixed-input runs each passed 42 gameplay scenarios. Both fighter roles execute all 12 cards, blocking, dodging, projectile combo/super damage, confirmed melee super, late projectile collision while a newer jab still plays, facing swap, fatal strike and reset. Both late-wave fatal cases preserve the new jab and finish native KO independently of frozen physics. Taikou inputs execute discard/select/reveal/resolve through production methods, with player wins, enemy wins, draws and EX fatal hits. Reveal never applies damage. Round over runs the production terminal branch; no directly sampled pose is applied by this live harness.
- `baseline-vs-current-off.json` preserves exact comparison findings. Post-cooldown draw RNG differs after separating visual RNG in current production. Ordered card/hit/super event content, settled HP, round wins, ranks, winner, damage, rage and EX match across all 42 scenarios. Exact old seed replay is therefore not claimed.
- `off-vs-on.json` compares the same current source version. All 38 realtime scenarios match exactly. Four taikou scenarios differ in approved resolve/contact hitstop and HUD combo timing; ordered gameplay events and settled rules match in all 42 cases. Exact wall-time equivalence of those taikou scenes is not claimed.
- Real direct-pose rendering: `shots/core` has 188 nonempty images and `reports/core-boards` contains stance/jab/cross/sweep boards/GIFs; `shots/all-poses` has 2144 nonempty images covering all 19 clips, both roles and both facing directions, with 38 boards/GIFs under `reports/all-pose-boards`.
- Real live rendering: `shots/live-core` contains continuous frame captures for 16 gameplay scenarios and `reports/live-boards` contains boards/GIFs. `shots/live-wave-final` adds both-role projectile collisions with a newer jab active and both-role late fatal waves, with boards/GIFs under `reports/live-wave-boards`. `current-on-visual-timing.json`, `live-core-visual-timing.json` and `live-wave-final-visual-timing.json` pass runtime contact endpoint, taikou contact hold, stale-action prevention and KO end/reset checks.
- `shots/live-final-extra` adds six final-code scenarios with explicit post-reset images and source motion hashes; `reports/live-final-extra-boards` contains their GIFs/boards and `live-final-extra-visual-timing.json` passes. Actual reset example: `shots/live-final-extra/player-fatal-facing-reset-f0080-foe.png`.
- Root was notified of first-pass framing concerns: player's lower boot touches/crops at the default SubViewport bottom, and foe's jab contact fist approaches/crosses the left border. Core image statistics include exact border alpha counts to help locate these frames; these are review flags, not a skin-quality certification. Root should repeat captures after camera/pose adjustments.

## Repeatable commands

Run from the task folder using PowerShell:

```powershell
./tools/launch_native_qa.ps1 -Mode rest
./tools/launch_native_qa.ps1 -Mode capture -OutName core -Clips 'stance,jab,cross,sweep'
./tools/launch_native_qa.ps1 -Mode capture -OutName all-poses -Clips all -Facing both -TimeoutSeconds 600
./tools/launch_native_qa.ps1 -Mode live -OutName current-off
./tools/launch_native_qa.ps1 -Mode live -OutName current-on -ThreeD
./tools/launch_native_qa.ps1 -Mode live-render -OutName live-core -ThreeD -Scenarios 'taikou-player,taikou-enemy,taikou-draw,player-fatal-facing-reset,foe-fatal-facing-reset,player-wave-new-action,foe-wave-new-action' -Stride 1 -TimeoutSeconds 600
```

Use the bundled Python path from `contracts.md`:

```text
python tools/native_qa_images.py --capture shots/core --out reports/core-boards
python tools/native_qa_images.py --live shots/live-core --out reports/live-boards
python tools/compare_native_live.py reports/current-off reports/current-on --out reports/off-vs-on.json
python tools/compare_native_live.py reports/baseline-off reports/current-off --out reports/baseline-vs-current-off.json
python tools/check_native_live_visuals.py reports/current-on project/data/combat_motion_3d.json --out reports/current-on-visual-timing.json
```

Direct native capture saves continuous integer frame sequences plus fractional samples around every authored phase key, both roles at production default cameras, optional reversed facing, and native pose/frame metadata. Boards mark authored keys/contact and GIFs show every integer frame; GIF timings alternate 10/20ms to average 60fps, and direct captures also produce 20fps `-slow.gif` previews. New runs record SHA-256 hashes for the motion data/library, both GLBs, driver/layer, and live integration scripts. Live captures read `arena.last_visuals`, fighter presentation snapshots and context from the real production state at each recorded tick; screenshots wait for `RenderingServer.frame_post_draw`. Fatal scene resets now capture an additional post-reset frame, including whole-arena images when the frame number is divisible by six.

## Pending visual acceptance

Repeat a complete-data capture after any subsequent production pose/camera changes. Review all 19 clips on both actual skins, native guard, each authored key/phase boundary/extremum, continuous transitions, reversed facing, contact/overshoot, foot support, shoulder/elbow/hip/knee seams, cloth strain and clipping. Current image tooling checks nonempty alpha and labels observations; it deliberately does not use the legacy P5 player-only edge statistic as a certification of new poses.

Root has paused further full captures while correcting viewport framing, guard visibility and skin weights. Existing images document the initial implementation; they must not be presented as final art acceptance. Refresh real-render evidence with the new source hashes after root announces these changes ready.

Headless live results prove gameplay and numeric state only. Recorded live evidence includes fatal KO reaching frame 27 and clearing on reset, block/dodge, late wave collision/current jab, both taikou winners and draw, combo/super and facing swap. Root performs frame inspection and adjusts authored poses before installation.
