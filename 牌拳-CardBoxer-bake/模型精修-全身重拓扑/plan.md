# Blender character retopology implementation plan

> For agentic workers: use subagent-driven-development with disjoint ownership;
> this repository has no usable source Git history, so use hash snapshots.

**Goal:** two detailed editable characters with progressive fist/palm rendering,
compatible with Natural V2, validated and installed in the main game.

**Architecture:** character authors output editable Blender projects and raw GLB;
a canonical export bridge retains the original skin/node basis and transfers new
geometry/morph/material data. Runtime samples hand_grip on the existing pose clock.

**Tech stack:** Blender 5.2.0, Python/NumPy/Pillow, glTF 2.0, Godot 4.5 Compatibility.
**Spec:** spec.md.

## Global constraints

All values in spec.md apply. Work only inside this isolated task until guarded
main installation. Use immutable baseline source, shared contracts.md, genuine
geometry/visual evidence and explicit Godot logs. No unrelated Git initialization.

## Review focus

- Bone rest basis changes after Blender export, although static silhouette matches.
- New normals/UVs or shape keys introducing broken shading/interpenetration.
- Hand-only state changes lost by pose equality or rendering invalidation.
- Shape sockets and displayed hand diverging during ordinary blends/freeze/late FX.
- Boot sampling disappearing after mesh/surface or weight organization changes.

## Tasks

- [x] Task 0: snapshot installed V2, establish isolation, ownership and baseline checks.
- [x] Task 1: canonical raw->game GLB bridge, original-rig compatibility and asset checker.
  Files: tools/canonical_glb.py, tools/check_retopology_assets.py, reports/pipeline-report.md.
  Tests: original/raw import-export preservation, weights/morph bounds, changed topology,
  original 14-joint parents/rest/IBMs, runtime mesh/material/image budget.
- [ ] Task 2: player full-body authoring, UV/bake, skin and progressive hands.
  Files: tools/author_player.py, authoring/player/*, reports/player-report.md.
  Tests: baseline has no hand morphs and no new editable quad mesh; final geometry,
  UVs, hand poses, loop/body skin and same-light near/full renders verify improvement.
- [ ] Task 3: foe full-body authoring, UV/bake, skin and progressive hands.
  Files: tools/author_foe.py, authoring/foe/*, reports/foe-report.md.
  Same asset assertions and actual armor/hands/cloth comparisons.
- [ ] Task 4: hand scalar sampling, morph application, socket prediction, foe composite.
  Files: project/scripts/native_motion.gd, battle_presentation.gd, fighter_3d_layer.gd,
  data/combat_motion_3d.json, data/model_profile_3d.json, tests/hand_shape_check.gd.
  Test red: hand-only blend/freeze/sockets unsupported in baseline. Test green:
  phase boundaries, progressive coefficients, both roles, pause/hitstop/KO/reset.
- [ ] Task 5: canonical assets assembled, exact-rig and full motion/skin render checks.
  Files: project/assets/3d/{player,foe}-rigged.glb, tools/render/check helpers, reports/*.
  Run meaningful existing suites once on frozen final candidate; add both-mode3D
  integration and normal-spawn full match. Check all19/both-facing geometry and framing.
- [ ] Task 6: independent final review/fixes, performance/preview package, guarded install.
  Verify final main hashes and both-mode installed checks; retain editable Blender
  sources, V2 baseline, versioned before backup, receipt and delivery note.
