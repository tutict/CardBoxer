# Canonical retopology pipeline — Task 1 report

Task 1 API and checker are ready for root's final assembly. The complete scoped suite passed **19 tests in 13.629s, with 1 intentional expected failure** proving that the frozen baseline lacks the required hand targets. Actual unedited Blender import/export and canonical repacking passed for both roles. The currently audited author snapshots remain **rejected** for missing tangent bases, outside-hand NORMAL morph deltas, and player ORM AO mapping; they are not final assets.

This continuation resumed the existing implementation and the checksum boundary in `resume-snapshot.json`. It did not replace authoring files, alter the runtime project, promote GLBs, create a Git/worktree operation, start Godot, or touch user Blender windows/processes. All diagnostic assets and logs were written under `tools/`. The background Blender CLI exited normally.

## Interface and implementation

The exact contract remains:

```python
canonicalize(source_glb: Path, raw_glb: Path, output_glb: Path,
             sockets_json: Path, profile_json: Path) -> dict
```

`tools/canonical_glb.py` retains original nodes, scenes, skin metadata, the original 14-joint declaration/order, and all inverse binding matrix values. New raw geometry is expressed through `inverse(source_mesh_global) @ raw_mesh_global`; joints are mapped by exact names. Normal and tangent directions use their appropriate transforms and normalization; morph NORMAL/TANGENT values are recomputed as direction deltas. A regression exposed and fixed the previous morph tangent treatment as a plain linear differential. The fixture includes different nonidentity mesh frames, reordered raw joints, and an omitted unused neutral joint, while the final preserves the source neutral declaration and original rest basis.

The bridge now rejects unsigned-index format violations, fractional JOINTS_0 data, negative/non-normalized or extra nonzero weights, neutral influence, unknown body joints, and raw rest/bind error above 1e-5m. Input GLBs, socket input, and frozen baseline cannot be overwritten through its API. An actual failing test exposed the socket-path output collision before it was fixed. Source/raw/output/profile/socket/image and pipeline hashes are returned for provenance.

The bridge deliberately permits an unedited source without new hand morphs or atlases, so the coordinate/rig compatibility test can run independently of authoring. **Root must also run `check_asset`/the checker CLI before promotion.** A successful canonicalize call alone is not final acceptance.

`tools/check_retopology_assets.py` checks the exact original node/skin/scene contract, one skinned mesh and one triangle surface/material, <=80000 triangles, nonempty geometry, degenerate triangles, normalized unit normals, UV0 atlas bounds, orthonormal tangent XYZ with W +/-1, four normalized influences, neutral zero, new indexed geometry, rest deformation <=1e-5m, and sole Y deviation <=.02m. It verifies exact target names/defaults, target accessor shape/finiteness, nonempty grip POSITION targets, and morph locality. Malformed skin/accessor data returns a failed report rather than escaping as a crash.

The material check requires three distinct embedded 4096x4096 PNG images for base color, tangent normal and ORM, with occlusion using the same ORM image and all channels using UV0. PNG validation now verifies all chunk bounds/CRCs, IEND, the complete zlib payload, legal encoding, scanline sizes and filter bytes; a header-only truncated PNG is rejected. The checker does not judge whether the baked pixel detail is visually good.

## Hand envelope and contact checks

The earlier checker inferred hand start from upperarm length *.55. Actual foe geometry disproved that assumption: it produced a cutoff near local Y .30m while authored hand vertices extend .196-.356m. A valid-hand false-rejection regression was recorded before fixing it.

The final envelope is derived from immutable source forearm geometry: original own-forearm influence >=.25; distal start is half the maximum original forearm-local Y; original vertices distal to this start define a local XYZ bounding box expanded by .02m. Candidate vertices must satisfy their own forearm influence, distal start and all XYZ bounds. This keeps body/boots/opposing hand excluded and prevents a displaced forearm-weighted vertex from authorizing morphs arbitrarily far from the original hand. This is a geometric envelope, not a semantic finger segmentation proof; root's visual hand review remains necessary.

| Role | Front distal Y | Rear distal Y | Front envelope vertices | Rear envelope vertices |
|---|---:|---:|---:|---:|
| Player snapshot | .192037m | .193876m | 1723 | 1729 |
| Foe snapshot | .184782m | .181667m | 1181 | 1177 |

POSITION/NORMAL/TANGENT target components above 1e-8 count as nonzero for locality. This tolerance was **not loosened** to make the author snapshots pass. Final-envelope diagnostics show outside-hand NORMAL maxima only 2.547093e-8 (player) and 2.547282e-8 (foe), with **zero outside-hand components above 1e-6**. Thus the snapshot's remaining morph-locality failures are numerical export residues, not observed material body shading changes. Larger normal changes on stationary vertices (roughly 80 per player hand, 87 per foe hand above 1e-6) are within the final physical hand envelope and should be retained. The raw exporter contains small normal residues up to 1.192093e-7; authors/root were told that clearing only sub1e-6 export noise can meet the exact outside-zero contract without discarding real hand normal changes. Exact measurements are in `tools/pipeline-normal-residue-diagnostic.json`.

Sockets are converted Blender world Z-up `(x,y,z)` -> glTF world Y-up `(x,z,-y)` -> original forearm-local. The checker measures point-to-triangle distance on the corresponding deformed hand at open/half/closed and rejects errors >.02m. After the envelope correction, all six snapshot sockets per role were on the visible hand surface, with maximum error <1.6e-16m. Quarter/three-quarter interpolation and posed contact are owned by root's runtime checks.

## Actual Blender roundtrip evidence

Executed with **Blender 5.2.0 LTS**, build hash `fbe6228777e7`, using the installed CLI:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python 'tools\pipeline_blender_roundtrip.py' 2>&1 | Tee-Object -FilePath 'tools\pipeline-blender-roundtrip.log'
```

The helper imports each frozen baseline with no mesh/armature edits, then selects only the imported skinned mesh and body armature and exports with skins/morphs enabled, animations/apply disabled and Y-up enabled. The importer also generates an `Icosphere` bone-control mesh; the initial diagnostic assertion exposed it. Selection was corrected to the skinned body, preserving unedited geometry and avoiding exporting the auxiliary control. This was a diagnostic selection fix, not an authored mesh change. The exporter logged its existing source-material warning about multiple image nodes for a texture sampler; that warning is retained in the log.

Source and raw mesh-global matrices were inspected and are identity in these real assets. Raw roundtrip nodes and IBMs differ from source for both roles, confirming why the source basis must be restored. Final nodes, scene and skin contract match source, and IBM arrays match bit for bit. `neutral_bone` remains joint 14/node13 under the source armature node14, independently of the 13 driven body bones; its original rotated global transform is preserved, not changed to identity.

| Role | Source/export vertices | Triangles | Symmetric max vertex error | Canonical rest/bind error | Raw-to-final rest transfer |
|---|---:|---:|---:|---:|---:|
| Player | 57934 / 57940 | 79986 | 1.094526e-6m | 7.060052e-7m | 5.131984e-7m |
| Foe | 64059 / 64065 | 79998 | 9.177003e-7m | 4.454003e-7m | 3.332642e-7m |

The six extra export vertices per role are seam duplicates. Comparisons use symmetric nearest position distances to handle exporter vertex ordering/splitting, rather than incorrectly treating an index seam as a physical hole. Both source GLB hashes were unchanged before/after. Geometry and rest comparisons are below the required 1e-5m. These are roundtrip diagnostics; their sockets are marked diagnostic-only and are not author contact calibration.

Full evidence: `tools/pipeline_roundtrip/blender-roundtrip-provenance.json`, the two `*-roundtrip-report.json` files, `tools/pipeline-real-roundtrip-tests.log`, and the final suite log. The original global/local node and skin inventory is in `tools/pipeline_author_audit/source-contract-inventory.json`.

## Tests and red/green history

The initial existing 5-test run passed after approved escalation. Running Blender Python in the managed sandbox denied fixture file access even in the owned tools directory; that original failure is captured in `pipeline-resume-initial.log`. Re-running the same scope outside the sandbox passed in `pipeline-resume-initial-approved.log`. No code workaround or unrelated process termination was used.

New behavioral failures were observed before production fixes:

| Log under tools/ | Observed failure before fix |
|---|---|
| `pipeline-resume-red.log` | Truncated PNG accepted; bad tangent/UV/material UV accepted; remote weighted morph accepted; malformed morph escaped |
| `pipeline-resume-red-binding.log` | Raw rest-bind drift accepted; transformed morph tangents incorrect; malformed skin escaped |
| `pipeline-resume-red-weights.log` | Fractional/float joint storage and negative extra weights accepted |
| `pipeline-resume-red-envelope.log` | Anatomically valid hand rejected because of unrelated upperarm length |
| `pipeline-resume-red-overwrite.log` | Output GLB could replace input socket JSON |

`pipeline-resume-green.log` records the intervening green suite. Final command:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' -m unittest discover -s tools -p 'pipeline*_test.py' -v 2>&1 | Tee-Object -FilePath 'tools\pipeline-final-suite.log'
```

Observed: **19 tests; exit0; OK (expected failures=1)**. This includes both actual Blender roundtrip tests and all compatibility/acceptance regressions. The expected failure explicitly demonstrates missing baseline grips; it is not a waived candidate failure. No Godot test/render instance was started by this worker. Root already owns the game suite, animation, actual skin/contact and performance acceptance.

## Current author snapshot audit

Executed `tools/pipeline_author_audit.py` with Blender's bundled Python; outputs are diagnostic-only under `tools/pipeline_author_audit/`. Both raw and socket hashes stayed stable during that audit. Authors are concurrently refining these inputs; root must rerun canonicalize and the checker against the final hashes.

| Metric | Player snapshot | Foe snapshot |
|---|---:|---:|
| Export vertices | 59195 | 65417 |
| Triangles | 73575 | 69468 |
| Degenerate triangles | 0 | 0 |
| Weight sum max error | 5.215406e-8 | 5.215406e-8 |
| Neutral visible influence | 0 | 0 |
| Rest/bind max error | 7.060052e-7m | 4.452979e-7m |
| Sole Y deviation | 6.867822e-10m | 4.407750e-7m |
| Image dimensions/payloads | 3 valid PNGs at 4096² | 3 valid PNGs at 4096² |
| Original rig/nodes/IBMs | exact | exact |
| POSITION locality / open-half-closed sockets | pass | pass |
| Final acceptance | **FAIL** | **FAIL** |

Final snapshot error codes: player `tangent_basis`, four `morph_hand_only` NORMAL noise entries, `orm_occlusion`; foe `tangent_basis`, four `morph_hand_only` NORMAL noise entries. Full per-target counts and local envelope bounds are in the two acceptance-report JSON files. No material or rig gate was disabled to accommodate them. Both author workers received the corrected envelope and precise noise measurements; significant in-hand normal changes are not a rejection finding.

## Hashes and recoverability

| Artifact | SHA256 |
|---|---|
| Frozen player source | `d4548f09c017ca65b1620cdabf6f9e4532bfbbddd7519d25da8eb3cdab6e2e5b` |
| Frozen foe source | `08713ff745ab490396cd150f4e91617055c6a648cf85dd9fdcd28c532b76cd18` |
| Player unedited raw roundtrip | `9526f40d8076c6823149e11b483279b2a8e895bedd4e8f4669f333ab5ed31682` |
| Foe unedited raw roundtrip | `3f1cc274567a3d098baf4530e9f076368a05eaa7be02a13068f7c46b85afc447` |
| Player canonical roundtrip | `94dafbaac56954f751a8e35cfb68d307bbba7708b6d0b5c07341c1de9a1f5a5f` |
| Foe canonical roundtrip | `8062a2314ec1bd81a8f43f6ccbe801f03d96f2b9a10913c8a88a0772f803f4e7` |
| Audited player raw | `4320e2bb2940d967af5b39dd2e76ed8cec21fb22e7388fe7d110b675d0c6927b` |
| Audited foe raw | `f25abddf501a257ab00283e205984ed10a433d8716f52cacad2640a5996ad824` |
| Player diagnostic canonical | `804e907be8c1f69de69ee0f735a825aedcd23ac4c938998abf2b49e2c54328bd` |
| Foe diagnostic canonical | `67f71b3e32e9988b8047fcddccb2644ea82e1279892063db5977251f0c81f75e` |
| Final canonical_glb.py | `d5d7b5f4aa9c540144ee225e954757ebb6fc4e266846b909ddff81c6d63b0634` |
| Final check_retopology_assets.py | `ea2cc1f1e696a44a082918fbfc15aef7cc2ebe6d20d7f32995099f7ba0531384` |

`tools/pipeline-final-manifest.json` records all owned script hashes and the pre-resume hashes. Unified diffs against the preserved canonical/checker snapshots are `tools/pipeline-diff-canonical_glb.py.patch` and `tools/pipeline-diff-check_retopology_assets.py.patch`. The frozen source SHA256 values match `baseline-manifest.json`; original snapshot scripts remain available for recovery.

## Practical limits and remaining acceptance

The script design remains dependency-light (NumPy plus Python standard library; no bpy in the bridge/checker). Tests exercise real buffer payloads and independent fixtures, including a complete decodable PNG and source/raw frame mismatch. Read-only validation fails closed on malformed input. The existing binary builder retains unused raw buffer segments/accessors while appending canonical data; this increases file size but does not change live mesh surfaces. It is not a minimal-size GLB optimizer.

The hand envelope depends on the existing source forearm-local +Y anatomy and weights. It is appropriate to these two canonical sources and has regression coverage for differing arm proportions and foreign/remote morphs; it is not a general semantic anatomy detector. PNG validation proves integrity/encoding, not bake appearance, fine detail, normal-map orientation or AO quality. Tangent validation proves an orthonormal exported basis, not exact per-pixel bake consistency. No automated claim is made about watertight physical surfaces, meaningful quad loops, clean intermediate fists, closed thumb/web topology, overlap/self-intersection, outfit/face improvement, or absence of visible cuff artifacts; author/root visual review supplies that evidence.

Root must rerun final stable raw inputs, inspect open/.25/.5/.75/closed hands and all19 clips/both facings, validate actual posed contact/soles <=.02m, normal/slow previews, both modes, timing/events/freeze/reset, and same-machine average>=59FPS/p95<=20ms/pose<=2ms per role. Final packaging, runtime profile merge, textures, editable .blend review and guarded installation remain root/author work. The pipeline did not install any current rejected snapshot.
