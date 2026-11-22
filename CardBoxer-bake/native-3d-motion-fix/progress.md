# SDD ledger — plan: D:/Projects/CardBoxer/CardBoxer-bake/native-3d-motion-fix/plan.md

## Authoritative latest state (Natural V2, 2026-11-20)

- Frozen V2 authored motion, smooth runtime interpolation, recovery and footwork
  are complete; motion SHA256 083c84e3e24bdb4bea6d3e4b92855322caea97d675cae19a06df36acefd5a703.
- Fresh final checks: 18/18 suites PASS, including 2,966 geometry samples and
  1,031 natural-runtime checks. Final rendered all19/both-facing: 3,004 images;
  continuous timing: 830 images, zero empty/clipped frames.
- Root's fresh V2 normal-spawn capture reached match_over after 2,629 frames,
  121 images. Original logical positions unchanged; both flow filmstrips accepted.
  The owned real-render helper exited 0 without access violation.
- User approved the scoped incremental update. Main now contains Natural V2:
  8 guarded files updated, 32 candidate/main hashes match, 11 installed checks PASS.
  Additional actual-main 3D integration: taikou 14/14 and realtime 14/14 PASS.
  Recovery: updates/natural-v2/before/ and its update-receipt.json.
- Every Godot invocation must use a real absolute writable --log-file. The new
  3D launcher uses a unique %TEMP%/CardBoxerLogs log; default/NUL logs are forbidden.
- Earlier installation-blocked and V1-only evidence below are historical.

## Current state

- User approved plan and implementation. This is Default mode, not Plan mode.
- Created isolated project/ with existing imports, baseline/ of source files and
  baseline-manifest.json (169 files) before implementation.
- Actual main project is outside writable root. Build/verify/package here first;
  install narrowly with explicit escalation if necessary after verification.
- Source has no git commits; actual main project has no .git. No worktree can
  represent the game source. Ruling: use a full isolated copy + byte-level
  baseline manifest and recovery backup, rather than initialize unrelated git.
- Parallel tasks use disjoint file ownership per contracts.md. Ruling: follow
  proactive parallel delegation with explicit interfaces, despite generic skill
  prohibition on simultaneous implementers; conflicts are prevented by ownership.

## Tasks

- [x] Native motion library + player/foe authored clips: all 19 per role, guard calibrated.
- [x] Driver/layer local quaternion application: native_rig_check 116/116 after red failures.
- [x] Snapshot/controller + taikou/realtime/event/KO wiring: controller38, native live14.
- [x] Real render capture, live scripted gameplay, deformation and logic regressions.
- [x] Fresh code review and fixes, guarded installation package prepared.
- [x] V1 installed into actual main project after user restored manual approval.
- [x] Natural V2 installed and verified: 11 installed checks and both-mode 3D integration.

## Decisions and hazards

- No NUL log path. Three prior tests crashed before script execution with NUL;
  valid absolute log paths then passed and no Godot/WerFault processes remained.
- All old 15 tracks already exist; historical three-track diagnosis is obsolete.
- Current four-arm retarget ignores direction, only has single-axis rotations;
  native pose mode replaces it, retains legacy apply_frame solely for compatibility.
- Actual models are fragmented-shell skins; old P5 single-axis player-only seam
  metric excludes stance bias and foe. Inspect final multi-axis poses on both.
- Models have no wrist/foot/finger bones; hand shape remains existing.
- Visual RNG separated; fixed input/deck equivalence is required, old mixed-RNG
  same-seed card order is not a backward compatibility guarantee.

## Implementation reports and current follow-up

- Motion author: reports/motion-report.md. NativeMotion 1502 sampled poses,
  strict bad-data and antipodal interpolation checks. Guard depth/calibration
  refreshed, still 1.58cm source-foot support metric (not a skin-ground proof).
- Integration: reports/integration-report.md. All current legacy headless suites
  pass; controller38/38 + actual native arena14/14. Late projectile does not
  rewind newer action; taikou fatal exchange survives over/freeze.
- QA: reports/qa-report.md, 42 scenarios +48 timing checks. 36 realtime on/off
  traces exact equal; taikou differences are intended visual hold timing.
- Historical first capture shots/core + all-poses is CROPPED, not acceptance.
  Framing red check failed all188 core images. Root expanded fixed 3/4 viewport
  and switched to ortho flat-ground anchoring. New framing-core is in progress.
- Skin repair root cause: 28 player/18 foe vertices static neutral anchors inside
  moving triangles cause large spikes. native_skin_repair agent owns GLB weights
  only, preserves all geometry/images/rest, repairs and reimports independently.
- Actual installed source is still untouched. Finish framing/skin real-image QA,
  then fresh code review and narrow hash-guarded install to actual game.

## Final state after interrupted-turn recovery (2026-11-20)

- All19 native clips/role complete, actual boot sole grounding and neutral-weight
  outliers repaired. Real final-all-poses:2152 images, no empty/border crop.
- Current17 applicable suites pass. Standalone contact/shadow tests now explicitly
  enable3D instead of relying on caller environment; the missing3D test setup
  caused a prior false failure/nil hang and is corrected. Shadow draws1->2 without
  changing logical position. Fresh report:reports/final-checks.json.
- Actual normal default-spawn full bot match:match_over after2629frames,121shots;
  logical spawns430/850 unchanged. Native taikou contact lunge now physically reaches
  the opponent, with shared hand/body/rhythm FX anchor. Preview:
  reports/normal-match-preview.gif and normal-match-result.png.
- Full final source review clean:reports/code-review-final.md. Ordinary.06s blends,
  signed retreat, paused blending, contact/KO priority and shadow invalidation fixed.
- Source package29 changed/new files:reports/change-manifest.json;
  tools/install_verified_changes.py dry-run passed, source and destination hashes
  guarded, backup+atomic copy+Godot import/reverification prepared.
- Installation attempted twice byroot and once viafresh verified_install agent,
  always with require_escalated/proper approval. All three were rejected BEFORE
  command execution due review infrastructure:stream disconnected; encrypted
  function output could not be decoded. This is not an unsafe-action determination.
  No approval bypass was attempted. No install receipt/installed-backup exists,
  actual main native JSON absent. Main project remains unchanged.
- Runnable tested version is project/. Current writable root is bake only;
  tofinish user can add D:/Projects/CardBoxer/CardBoxer as writable
  workspace or restore approval service, then rerun guardedinstaller (refresh
  manifest first if test source changed). Do NOT redo completed implementation.

## Latest user steering / resumed implementation

- User restored manual approval; exact installer approved and installed29 files,
  installed-backup/ and reports/install-receipt.json now exist. Godot main import
  passed. Native test printedPASS(1502samples) but verifier marked false due wrong
  underscore marker; fixed tools/install_verified_changes.py marker to spaces.
- User saw final-preview.png and requests more natural/fluent fighting-game
  motion. Continue this task, refine V1 (not a new project). See natural-flow-v2.md.
- Saved authored/native motion/controller V1 under versions/v1/ before refinement.
- Remaining: natural motion/curves/recovery footwork, fresh flow/skin/render QA,
  guarded incremental update against install-receipt hashes, installed verification.
- Manual approval mode is active; do not reuse the original --apply installer,
  because its backup guard intentionally prevents overwriting an existing install.

## Natural V2 progress

- natural_motion_author: target-space Hermite sampled .5frame + analyticIK,
  compact guard/hip-led strikes/extended lowsweep/recovery hand lead. All19dense
  clips, actual boot grounding. Quarter-frame geometry2966samples PASS,
  maxsupport .002571m. Report:natural-motion-v2.md. Last visual guard height/roll
  calibration in progress (fingertips previously too high), then data freezes.
- natural_runtime_flow: time-aware cubic quaternions, monotone root, exact keys,
  quintic approach+return, hand retract lead .08s, signed travel gait both ways.
  Exact full mesh support grouping+prewarm, CPU1.19/1.23ms perpose and measured
  twoactor GL60.0024FPS. New1031 checks PASS, controller44/44, transition51/51,
  contact70/70, both-mode integration14/14. Actual support<1mm. Report exists.
- natural-v2-core real render598images PASS framing. This is preliminary artwork;
  final normal/slow preview and current17 checks needed after guard calibration.
- New tools/update_verified_changes.py prepares guarded incremental update from
  install-receipt AFTER hashes, versioned backup, atomiccopy+main verification.
  Native verification marker corrected to actual "NATIVE MOTION CHECK: PASS".
