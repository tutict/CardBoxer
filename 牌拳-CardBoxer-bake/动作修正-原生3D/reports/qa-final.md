# Final native 3D render QA

Ready: fresh actual-render captures, frame checks, native skin invariants, and reviewed fixed-input live previews are complete. Production scripts, motion data, and GLBs were not changed by this QA pass. The only source edit was the parent-authorized test initialization reorder in `project/tests/native_live_check.gd`: assign `battle_mode` before `root.add_child(a)` triggers `_ready`.

## Evidence and results

| Evidence | Fresh result |
|---|---|
| `shots/final-all-poses/manifest.json` | Real Windows GL Compatibility rendering on NVIDIA GeForce RTX 5080 Laptop GPU; completed; 2,152 PNGs; 19 clips × 2 actual GLBs × 2 facing directions = 76 combinations; every integer frame plus fractional authored-key/contact samples; all PNG writes succeeded. |
| `reports/final-capture-framing.json` | PASS: all 2,152 full 720×680 transparent captures nonempty and clear of the viewport border with 4 px padding. |
| `reports/final-all-pose-boards/image-review.json` | 38 labeled phase boards, 38 continuous GIFs, 38 slow GIFs; 0 tiny/empty images and 0 images touching a border. |
| `reports/final-skin-invariants.json` | PASS: full GLB byte preservation outside permitted JOINTS/WEIGHTS, normalized finite weights, bounded repair scope, neutral-weight removal, coincident seam consistency, preserved bind/rest deformation, and actual cached Godot 14-bone names/parents/rests. 98 authored keys checked per role across all 19 clips. |
| `reports/final-live42/summary.json` | PASS: 42 current 3D-on production-state-machine scenarios, 0 failures. These headless runs are gameplay/numeric evidence only. |
| `reports/final-live42-visual-timing.json` | PASS: 48 timing assertions across 42 scenarios. |
| `shots/final-live6-reviewed/summary.json` | Six real-rendered production-state scenarios: player cross, foe sweep, both taikou winners, player delayed-wave/new-jab, and reversed-facing foe fatal strike/reset. Four realtime scenarios were recaptured after the test-only initialization repair; two unaffected taikou captures retained. |
| `reports/final-live6-reviewed-visual-timing.json` | PASS: 10 assertions across the six actual-rendered scenes. Both taikou winners hold native wave contact at frame 17 for ticks 119–134. The delayed wave hits at tick 72 after the new jab starts; the jab remains current. Fatal KO reaches frame 27, holds, and clears on reset. |
| `reports/final-live-framing.json` | PASS: 1,802 actual fighter SubViewport PNGs, 0 empty/clipped captures. Opaque whole-arena screenshots are excluded from an alpha-border test. |
| `reports/final-live-initialization-comparison.json` | PASS: all six gameplay traces exactly equal before/after the test setup reorder, including hands, timers, hitstop and settled rules. |
| `reports/final-evidence-manifest.json` | Current production file hashes match all final direct and reviewed live capture hashes; preview paths, dimensions, frame counts, durations, and SHA-256 retained. |

The final motion-table SHA-256 is `391cf0ad5c83ee19938f8f4c3fc11b69ad4a8e0d054e387c62b060149df25d66`. Actual GLB SHA-256 values remain player `d4548f09c017ca65b1620cdabf6f9e4532bfbbddd7519d25da8eb3cdab6e2e5b` and foe `08713ff745ab490396cd150f4e91617055c6a648cf85dd9fdcd28c532b76cd18`.

## Rendered inspection

Inspected all 19 clips on both skins and both facing directions at contact, terminal, or displacement-extremum samples via `final-key-overview-1.png` through `final-key-overview-5.png`. Also inspected cross/sweep/reversed-jab phase boards, full-resolution cross/sweep and both-facing KO endpoints, and actual whole-arena normal/contact/wave/KO scenes. The corrected realtime screenshots display the realtime round banner rather than the stale taikou discard banner.

No long neutral-bone head-ribbon/cape spike or cropped body was visible in those inspected samples. Native guard, jab/cross reach, uppercut, low sweep and prone KO are distinguishable. Reversed facing keeps both complete silhouettes in frame. Sampled whole-arena stance, contact, wave, and KO frames place the supported sole/body at the visible floor/shadow without gross floating. Transparent direct-pose images alone cannot prove floor contact.

Residual original skin limitations remain visible: rigid open hands, faceted armor/cloth folds, and dense self-overlap in low sweep/KO. Quantitative remaining edge strain is player maximum 0.207440 m added length, 334 distinct edges exceeding 0.10 m; foe maximum 0.161468 m, 143 edges. These are reduced from the original neutral-outlier defects, but are not zero or a claim of perfect skinning. The fixed-input 85 px close-range setups substantially overlap fighter silhouettes, especially during taikou followthrough; natural spawn spacing and a full three-round match are checked separately by the parent task. The foe sweep scenario is an actual whiff, not a demonstrated hit.

This is sampled rendered inspection backed by complete captures, not a claim that every PNG was manually examined. No dummy/headless image was used as skin evidence.

## User-facing previews

- `reports/final-preview.gif`: 720×360, 152 frames, 7.6 seconds. Player/foe side by side, jab/cross/sweep/uppercut/wave/KO, explicitly slowed to 20 fps.
- `reports/final-preview.png`: compact six-clip contact/KO board.
- `reports/final-live.gif`: 768×456, 153 frames, 15.7 seconds. Six actual whole-arena scenarios at their recorded 10 fps sampling, followed by a labeled actual fighter-viewport reset sample held for 0.5 seconds. Fatal reset tick 80 is not divisible by the whole-arena capture interval of six ticks, so its final sample is explicitly a SubViewport composite.
- `reports/final-live.png`: six actual-state scene samples, including both taikou contact holds and completed KO.
- `reports/final-live-boards/`: all six reviewed live scenario boards/GIFs, including the actual reset images.

Historical `shots/core`, `shots/all-poses`, and their previews are not final evidence. The old four realtime images under `shots/final-live6` are superseded for whole-screen presentation by `shots/final-live-realtime-fixed`; the reviewed aggregate preserves explicit source paths for each of the six scenes.

The existing image helper was reused without editing it. Its hardcoded 276×370 phase tiles are too small for the new viewports at its default 0.64 scale, so the final pose boards invoke its `composited` helper at 0.38 scale; the complete source captures fit and remain unmodified. Live boards use 0.40 scale. All final preview composites fit their complete source viewports without clipping.

## Repeatable commands

Run from the task folder. Python is the bundled runtime named in `contracts.md`.

```powershell
$qaPython = 'C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1118-904-0_26.1118.904.0_x64__3k8sg7r9htsxt/dependencies/python/python.exe'
./tools/launch_native_qa.ps1 -Mode capture -OutName final-all-poses -Clips all -Facing both -TimeoutSeconds 600
& $qaPython tools/check_capture_framing.py shots/final-all-poses --out reports/final-capture-framing.json
& $qaPython tools/check_native_skin.py --verify --godot 'C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe' --json reports/final-skin-invariants.json
./tools/launch_native_qa.ps1 -Mode live -OutName final-live42 -ThreeD -TimeoutSeconds 300
& $qaPython tools/check_native_live_visuals.py reports/final-live42 project/data/combat_motion_3d.json --out reports/final-live42-visual-timing.json
./tools/launch_native_qa.ps1 -Mode live-render -OutName final-live6 -ThreeD -Scenarios 'player-card-cross,foe-card-sweep,taikou-player,taikou-enemy,player-wave-new-action,foe-fatal-facing-reset' -Stride 1 -TimeoutSeconds 600
./tools/launch_native_qa.ps1 -Mode live-render -OutName final-live-realtime-fixed -ThreeD -Scenarios 'player-card-cross,foe-card-sweep,player-wave-new-action,foe-fatal-facing-reset' -Stride 1 -TimeoutSeconds 600
& $qaPython tools/check_native_live_visuals.py shots/final-live6-reviewed project/data/combat_motion_3d.json --out reports/final-live6-reviewed-visual-timing.json
& $qaPython tools/compare_native_live.py shots/final-live6 shots/final-live6-reviewed --out reports/final-live-initialization-comparison.json
```

`final-live6-reviewed` contains six scenario JSONs copied from the explicitly listed original/fixed capture locations; screenshot paths still point to those actual capture files. For a fresh one-pass run with the corrected test harness, the `final-live6` six-scenario command produces the same current setup directly.

All helpers were launched hidden and exited normally. Owned Godot PIDs were 9612 (pose capture), 26640 (live42), 33164 (initial live6), and 11736 (four corrected realtime scenes). Engine/stdout/stderr logs are real files under `logs/final-all-poses-*`, `logs/final-live42-*`, `logs/final-live6-*`, and `logs/final-live-realtime-fixed-*`; skin stdout is `logs/final-skin-invariants-stdout.log`, with `logs/skin-import-check-engine.log` for cached skeleton verification. No global process termination, installation, or commit was performed. The existing Windows root-certificate-store warning appeared; no script/parse errors or capture failures appeared.
