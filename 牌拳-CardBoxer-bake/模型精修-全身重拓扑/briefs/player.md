# Player authoring brief

Read ../spec.md and ../contracts.md first. You own only tools/author_player.py,
authoring/player/** and reports/player-report.md. Do not write project/ or main.

Create a genuine full-body editable retopology and improve player face, hand,
clothing shape/edge quality and material response. Rebuild quad-dominant mesh,
appropriate eye/mouth/finger/body-joint loops, new UV atlas and 4K baked PBR.
Game target60k triangles, cap80k. Preserve silhouette and rig identity. Maintain
closed source surfaces/intentional component structure rather than blindly weld.

Progressive front/rear hands and raw export follow contracts.md. Analyze original
hand location/bone groups to build clearly segmented fingers and safe thumb fold.
Use high-detail sculpt/bake reference, manually/procedurally correct local mesh
quality after a base QuadriFlow step. Do not call an untouched source merely
retopology; record actual new connectivity and quad/triangle counts.

Keep user Blender untouched. Operate Blender5.2 background via owned helpers.
For any rig/hand/data ambiguity use contracts and judgment, record the decision.
Produce staged renders with exact source/candidate same camera/light near face,
hands and full-body, plus low wireframe. Inspect actual images and revise defects.

First verify baseline lacks required hand morphs/editable retopology; record the
failing acceptance then build. Before claiming DONE validate normalized weights,
4K maps, skin/material/morph export and full hand 0/.25/.5/.75/1 geometry. Coordinate
canonicalization with pipeline worker; do not wait idle on shared helper choices.
Return compact status and report path with actual tests/hashes/limitations. Do not
spawn your own reviewer; root will review. Any Godot test must use a real absolute log.
