# Retopology ownership and interfaces

## Ownership

- Root: spec/plan/ledger, all project runtime scripts/data/tests, final capture,
  review, package and main installation. Root alone replaces game GLBs.
- Pipeline worker: tools/canonical_glb.py, tools/check_retopology_assets.py,
  tools/pipeline_* only, reports/pipeline-report.md; no role authoring/runtime writes.
- Player worker: tools/author_player.py, authoring/player/**, reports/player-report.md.
- Foe worker: tools/author_foe.py, authoring/foe/**, reports/foe-report.md.
- Authors may each keep private helpers under their own authoring folder.
  Shared code needs explicit owner coordination. No main writes or user app changes.

## Raw author deliverables

For ROLE=player/foe, baseline/assets/3d/ROLE-rigged.glb is immutable input.
Output authoring/ROLE/ROLE-retopology.blend, ROLE-raw.glb, build-report.json,
contact-sockets.json, textures/*.png and near/full/wireframe comparisons.

Raw GLB selection contains only the new single mesh + original body armature;
export_skins=True, export_morph=True, export_morph_normal=True,
export_animations=False, export_apply=False, export_yup=True. Bake geometry
modifiers BEFORE establishing shapes. Use exact original body bone names for
vertex groups. Do not export high reference, sculpt mesh or auxiliary hand rig.
At most four normalized influences, neutral_bone has zero visible influence.

Raw mesh extras.targetNames must include exact grip_half_f, grip_f,
grip_half_b, grip_b names. Basis=open, defaults all0. All body/boot vertices have
zero hand deltas. Use physical finger segmentation and thumb placement, inspect
intermediate .25/.5/.75 hand states. Authoring file retains the source reference
and original skeleton, refined high detail, new quad-dominant low mesh, masks,
materials, shape keys and reproducible build provenance.

Sockets JSON:
{"version":1,"role":"player","space":"blender_world_z_up",
 "front":{"open":[x,y,z],"half":[x,y,z],"closed":[x,y,z]},
 "rear":{"open":[x,y,z],"half":[x,y,z],"closed":[x,y,z]}}
Each point is on the visible new hand (palm center for open, striking surface
for half/closed), computed in authored object's world coordinates at bind rest.
If another space is necessary, coordinate with pipeline worker/root BEFORE writing.

## Canonical export bridge API

canonicalize(source_glb: Path, raw_glb: Path, output_glb: Path,
             sockets_json: Path, profile_json: Path) -> dict

Re-express new mesh/morph geometry in source mesh bind space; map JOINTS by exact
bone name; preserve original node hierarchy, 14 skin joints and IBMs. Convert
Blender world Z-up socket coordinates through glTF world Y-up into source
forearm-local. profile_json output:
{"version":1,"role":"player","hand_sockets":{"front":{"open":[...],
 "half":[...],"closed":[...]},"rear":{...}}}
Runtime final model_profile_3d.json is {"version":1,"roles":{"player":profile,
"foe":profile}}. All sockets are canonical forearm bone-local.

## Runtime hand contract

Native pose adds hand_grip [front,back], numeric finite 0..1. Old pose data may
omit it (legacy .75 default). Body13 rotations/root and phase data are untouched.
0..0.5: half_weight=2*g, full_weight=0.
0.5..1: half_weight=2*(1-g), full_weight=2*g-1.
These same coefficients apply to geometry and open/half/closed contact sockets.
Pose equality, blending, clocks, driver application and render invalidation must
account for hands. Reference/support correction changes only allowed root Y.

## Execution

Blender CLI: C:/Program Files/Blender Foundation/Blender 5.2/blender.exe.
Use hidden/owned background processes for authoring; source never overwritten.
Every Godot invocation needs a writable real absolute --log-file under logs/.
Do not kill user Blender PID31084 or any process not launched by this task.
Reports must contain actual geometry counts, executed commands/logs, source and
output SHA256, what is visually improved, and material limitations honestly.
