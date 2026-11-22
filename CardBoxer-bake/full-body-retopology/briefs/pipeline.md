# Canonical GLB pipeline brief

Read ../spec.md and ../contracts.md first. Own tools/canonical_glb.py,
tools/check_retopology_assets.py, tools/pipeline_* and reports/pipeline-report.md.
Do not edit authoring role files, runtime project or main. Root alone promotes assets.

Implement the exact canonicalize API in contracts. Character authors export raw
single low mesh+body armature with progressive morphs/PBR and Blender world-Z-up
hand socket JSON. Use original baseline GLB node/skin/IBMs as canonical. Map new
geometry from raw mesh bind frame to source frame, remap raw joint indices by
exact bone names, preserving all original joints, parents, local transforms and
binding matrices. Blender-importer guessed bone axes must never change q_rest*q_delta.

Allow real new geometry/UV/material/weights/shapes, prohibit original rig drift.
At most4 normalized influences, neutral zero. Exact morph target names, target
deltas outside hand/boots0, one skinned mesh/surface/material and3x4096 PBR images,
<=80000 triangles. Convert sockets to original forearm-local profile schema.
Raw Blender source armature may omit unused neutral in raw skin; final must retain
the original14-joint declaration and independent neutral transform.

Write meaningful fixture/real-source compatibility tests before bridge code;
record missing-morph acceptance red against baseline. Inspect original and raw
gltf mesh-global matrices/skin semantics rather than assume source frame identity.
Perform actual unedited Blender import/export roundtrip in owned background helper,
canonically repack and verify rest deformation and original skeleton contract;
canonicalized roundtrip vertices should match original within1e-5m. Intermediate
geometry output is tools-only; do not overwrite baseline or project GLBs.

No source Git commits available: use checksums/diff manifests and concise report.
Communicate API readiness to root and authors. Do not start duplicate full render
or Godot processes unless needed for imported rig validation; all Godot commands
must have real absolute writable logs. Preserve user Blender PID31084.
