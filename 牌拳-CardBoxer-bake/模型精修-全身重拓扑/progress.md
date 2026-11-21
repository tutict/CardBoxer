# SDD ledger — plan: C:/Users/tutic/Desktop/学习资料/牌拳-CardBoxer-bake/模型精修-全身重拓扑/plan.md

## Status

- User approved full retopology, progressive hands, game+near detail and foe clarity;
  then explicitly asked implementation. No further execution confirmation needed.
- Isolated project/ and immutable baseline/ created from actual installed Natural V2:
  216 source files and baseline-manifest.json. Archived current installation receipt
  and original imported-rig probe. Main remains unchanged during authoring.
- No useful source Git history; main has no .git. Ruling: isolate by full copied
  project and hash-guarded baseline/receipts, following the established V2 workflow.
- Ruling: use proactive parallel implementers with disjoint file ownership in
  contracts.md. This overrides generic skill serialization; clear interfaces prevent
  shared-file conflicts. Root selects existing model/execution defaults.
- Writing plan is an execution breakdown of the already approved design; do not
  reopen scope/method consent from generic skill prompts.
- Source V2 rig: 14 bones,13 driven, neutral unweighted; one mesh/surface/material,
  about80k triangles/role and3x4K textures. Index islands are UV/normal splits, not holes.
- User's Blender PID31084 is preserved. All task Blender/Godot processes are owned
  helpers; Godot always requires explicit real logs, never NUL/default.

## Preflight interfaces

| Pair/task | Interface/check | Ruling |
|---|---|---|
| Pipeline/Player | raw.glb+morph names/socket coordinate space | exact contracts.md; independent files |
| Pipeline/Foe | same schema, separate role outputs | exact contracts.md; independent files |
| Pipeline/Runtime | canonical forearm-local profile and original skeleton | root assembles both profiles; no raw-basis leakage |
| Player/Runtime | hand-only four morphs; body/boot delta0 | body motion remains V2; old body arrays compared |
| Foe/Runtime | same morphs plus dark display adjustment | shader only changes foe local composite |
| Task1 | canonical rig metadata vs Blender axis changes | canonical source skeleton is authority |
| Task2 | full retopo vs historic UV index-island counts | rebuild for loops/quality, not imaginary holes |
| Task3 | low mesh vs high-detail authoring | separate authoring layers; export selected low only |
| Task4 | shape-only changes vs old dirty/equality | include hands in all displayed state handling |
| Task5 | boot sampler surface0 vs material split | final single mesh/surface, boots retained |
| Task6 | installation vs writable-root boundary | finish candidate first, narrow manual approval if required |

## Task tracking

- [x] Task0:216 files copied/hashed; clean candidate import exited0 and baseline
  natural runtime1031/1031 passed. Known certificate/editor-settings diagnostics
  are environment warnings, not script/import failure.
- [x] Task1: canonical pipeline and asset checker; final character input acceptance
  remains Task5. Independent fix round1 re-review passed all four axes.
- [ ] Task2: player authoring.
- [ ] Task3: foe authoring.
- [x] Task4 implementation: meaningful initial RED9 missing-hand behaviors;
  GREEN151/151 hand tests; existing natural runtime1031/1031 still passes.
 1502 hand-annotated keys preserve all original body/phase data exactly. Final
 asset-dependent/socket/render checks and independent task review remain.
- [ ] Task5: final geometry/render/logic/performance verification.
- [ ] Task6: review, delivery and guarded main installation.

## Runtime notes / infrastructure

- Initial three gpt-6-astra implementers failed before any work due service high
  demand. Ruling: use available gpt-6.1-sol high workers for pipeline/player/foe;
  ownership unchanged, root independently verifies artifacts/review. No duplicated work.
- Prior implementers are no longer live. Resumed on the user's 2026-11-20
  request to continue dual-character full-body retopology and refinement;
  current implementers: retopo_pipeline, retopo_player, retopo_foe.
- New scripts/hand_shape.gd owns validation, progressive weights and sockets.
  Layer applies four morph coefficients and rejects invalid scalar before body
  application. Old assets/data remain compatible until canonical assets promoted.
- Global body/phase invariance is checked by author_hand_grips.py against baseline.
- Model profile does not exist yet; no original source/main assets were replaced.

## Resume verification / current boundary

- Existing working authoring assets were found, not recreated: player at 17:26,
  foe at 17:28. Pre-resume script copies and artifact hashes are preserved in
  reports/resume-snapshot.json and reports/*-resume.py for review/recovery.
- Fresh checks: HAND SHAPE 151/151 passes; HAND ASSET 5/10 fails as expected
  because project still has legacy assets and no canonical model profile.
  Logs: resume-hand-shape-engine.log, resume-hand-asset-engine.log.
- Actual image inspection found severe patches/broken surfaces on player face,
  eyelids, cheeks, bangs and neck versus clean immutable source. Player owner
  is diagnosing these before any asset promotion. Foe cuff near image and raw
  tangent export warning also require verification/correction.
- Ruling: retain existing copied-project/hash-snapshot isolation and approved
  disjoint parallel ownership; use the existing spec/contracts/plan/ledger as
  the authoritative task state. Do not introduce a competing Git or protocol
  workspace. Product checks cover authoring geometry, canonical compatibility,
  runtime integration, visuals and performance before guarded publication.

- Fresh continuous body comparison: 24,034 checks across 1,502 integer/fractional
  samples (all19 clips, both roles), zero failures and no measured body/root
  sampler drift. Harness tools/check_hand_body.gd stays outside published tests.
- Root prepared owned final runtime suite, all-key skin/morph/sole comparison,
  real motion/near/brightness/match/performance capture and evidence packaging
  tools. Capture scripts parse; final asset-dependent execution remains pending.
- Task1 implementation report: 19 tests pass, one intentional baseline expected
  failure; genuine Blender5.2 source roundtrip/repack is <1.1e-6m for both roles.
  Source-backed hand envelope corrected a false foe rejection; residual outside
  NORMAL components are only ~2.55e-8. Authors retain real in-hand normal changes
  and must clear export noise/complete tangent and player AO input gates.
- Task1 independent review (reports/pipeline-review.md): request changes on four
  reproduced P2s: invalid triangle accessor storage, reads beyond bufferView,
  indexed PNG missing PLTE, and output/staging/external-image input collisions.
  Fix round1/5 is assigned to the original pipeline owner; no final pipeline
  acceptance or promotion occurs before scoped re-review.
- Latest user steering: asks whether palm bending is reversed. Root confirmed
  at least one mirrored hand has reversed flexion/outward thumb in actual current
  images. Both authors must prove palm-normal direction and four fingers curling
  toward palm, with thumb outside fingers; inspect dorsal/palm/three-quarter views
  and intermediate states. Body rig/quaternions remain governed by original spec.
- Player continuation build2 (00:12 Nov21) still visibly fails face acceptance:
  patches persist on bangs, eyelids, cheeks/jaw/ear/neck. Source cap-walker caused
  69 edges with3/4 linked faces; author is separating geometry/custom normals/
  texture causes. Export also warns temporary mesh node_0.005 invalid. Root asked
  for latest low-only clay/base/no-custom-normal diagnostics before further full
  bakes, and for final validation on newest saved file (old16:47 validation stale).
- Active resumed author workers: retopo_player and retopo_foe. Pipeline owner
  retopo_pipeline is in fix round1; review_pipeline completed initial review.
  Do not duplicate role work or promote still-invalid author snapshots.
- Task1 fix round1/5 complete: F1-F4 addressed, zero open/new actionable findings;
  reports/pipeline-rereview-r1.md records independent four-axis PASS. Final suite
  33 tests/exit0 with one intentional baseline expected failure; real Blender
  roundtrip/source hashes still match, vertex transfer <1.1e-6m. No rerun by root
  or reviewer claimed; the observed source logs and current hashes support gate.
- Parent interruption recovery on Nov21: rechecked current files/logs and reused
  existing workers via followup. Player has latest topology/clay diagnostics at
  01:08/01:13; foe source figure-eight cuff correction is preserved in resume
  helper/working blend. Raw outputs remain incomplete (player00:12, foe17:28).
  User-owned morning Godot PID16584 is preserved. No finished task was recreated.
