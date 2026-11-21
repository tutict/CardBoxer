# Canonical retopology pipeline — Task 1 report

**2026-11-21 review round 1 update:** F1–F4 have focused fixes and passing regressions; the full scoped suite now records **33 tests in 24.657s, OK with 1 intentional expected failure**. Root's independent re-review is pending. The original report below remains historical evidence; the dated appendix records the reviewed boundary, fixes and fresh validation. This is not final character/runtime promotion approval.

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

## Review round 1 fixes — 2026-11-21

Read `reports/pipeline-review.md` and reviewer-owned characterization `results.json`/`probe.py` before editing. Applied the receiving-code-review, TDD and verification workflows. The reviewer evidence and probes were left unchanged. Before edits, copied all six reviewed scripts and this report into `tools/pipeline_review_round1_before/`; its `manifest.json` records the exact SHA256 boundary. Only `canonical_glb.py`, `check_retopology_assets.py`, `pipeline_test.py` and this report changed. No Git, worktree, subagent/reviewer, authoring/runtime/main writes, Godot invocation, or user Blender process/window manipulation occurred.

### F1 — [P2] Validate triangle accessor storage before casting/flattening — fixed

Added shared `GLB.triangle_indices(vertex_count)`. It requires an in-range accessor index, unnormalized unsigned byte/ushort/uint SCALAR storage, nonempty count divisible by three and in-range vertex values before integer conversion. Bridge and checker use this gate for source and raw/candidate containers; reflection uses already validated indices, so it cannot coerce an invalid accessor into apparent validity. Geometry equality comparison uses the validated original indices. Existing position/joint/frame/skin/morph math was preserved.

The focused RED run recorded eight independent checker/bridge failures for fractional FLOAT, UINT16 VEC3, normalized UINT16 and signed INT16 index storage. GREEN passed both tests, including valid unsigned SCALAR storage at all three widths. An additional source-container regression failed once before the same gate was applied to the original/source read; its GREEN run passed. This closes the two supplied reviewer index probes and the named normalized/signed variants.

### F2 — [P2] Bound accessors to their declared bufferView — fixed

The shared reader now validates integer/nonnegative view/accessor/buffer indices, offsets and positive counts/lengths; complete view containment in its backing buffer; accessor containment in that view; component/matrix alignment; and supplied stride size, 4-byte alignment and glTF stride range. Reads use the verified view layout instead of relying on a larger backing buffer to conceal a short declaration.

Sparse index/value reads use the same bounds calculation, with no bufferView stride/target; sparse counts must be positive and <= accessor count, index storage unsigned, and indices strictly ordered, unique and within range before assignment. Matrix elements honor glTF column padding for small integer components. Tests preserve valid interleaved VEC3, sparse replacement and a padded MAT3 UINT8 payload, in addition to the existing real MAT4 float binding data.

RED recorded 15 assertion failures and 6 exceptions for missing typed validation, including the reproduced four-byte POSITION view. GREEN passed all three focused tests across short views, backing-buffer crossings, negative/fractional/misaligned offsets/counts, invalid strides and sparse storage/order/range cases. Exceptions in RED came from the previous reader's TypeError/IndexError rather than test syntax; the corrected boundary returns ValueError and the final checker reports failure.

### F3 — [P2] PNG scanline checks do not establish valid indexed PNG encoding — fixed

Chose the review's explicit supported-format alternative: PBR atlases accept **RGB (type2) or RGBA (type6), 8/16-bit PNG**. Indexed/grayscale encodings are deliberately rejected rather than claiming a palette decoder. CRC/full zlib/filter/scanline validation remains; added chunk type/reserved-bit validation, rejection of unknown critical chunks, contiguous IDAT requirement, legal optional PLTE constraints/order, and legal RGB transparency metadata (forbidden for RGBA). Both noninterlaced and the existing Adam7 scanline layouts remain supported.

RED recorded seven failures: missing-palette indexed PNG, unknown critical chunk, split/noncontiguous IDAT, late palette, invalid palette length, RGBA tRNS, and the actual candidate image acceptance path. GREEN passed both focused tests, including valid RGB/RGBA at 8 and 16 bits. This is structural support for the specified PBR channel images; ancillary metadata is not a universal PNG standards audit and pixels are not a bake quality assessment.

A read-only check of all six actual author atlas payloads also passed: player raw `48f163b6f6784f28f66c67f1fb7e178c31b98e8e021b7261847a678bd990c730` has three RGBA8 (type6) 4096² PNGs; foe raw `f25abddf501a257ab00283e205984ed10a433d8716f52cacad2640a5996ad824` has three RGB8 (type2) 4096² PNGs. Both raw hashes stayed unchanged during that read. This checks PNG compatibility only, not current full author acceptance or the concurrently ongoing visual fixes.

### F4 — [P2] Include staging files and external raw dependencies in collision protection — fixed

Before any output write, enumerate resolved source/raw GLB files, external buffer/image resources from both containers, socket input and pipeline source; compare both outputs and CLI report paths against that set and each other, including existing hard-link aliases. Local resource URI percent escapes resolve consistently for reading and collision protection. Unsupported nonlocal resource URIs fail rather than silently hiding a dependency. All input SHA256 values are captured before mutation and returned as `immutable_input_sha256`; source/raw/socket/pipeline hashes no longer depend on post-write reads of potentially consumed paths.

Replaced predictable `<output>.tmp` staging with `tempfile.mkstemp` exclusively created random sibling files, write/flush/fsync, atomic replacement and cleanup of only that allocated file. GLB, profile and CLI report use this writer. A supplied source named `out.glb.tmp` is now safely allowed because that pathname is no longer used as staging; successful assembly preserves its bytes. Output/profile/report collisions with real dependencies are rejected before either output is created.

Both CLI report paths are protected. Checker report writing requires all input containers/dependencies to be inspectable; it will fail before writing if that dependency set cannot be established. It does not suppress an unsupported URI and discard an otherwise valid external input from protection. Programmatic `check_asset` still returns a failed report for malformed candidates.

Final focused RED recorded 17 failures and 2 exceptions: legacy temporary source consumed, eight source/raw external image/buffer output/profile collisions, five named bridge report collisions, external image report collision, three checker input report collisions, and encoded-resource reading. GREEN passed all five focused tests. A follow-up mixed supported/unsupported-URI test exposed a partial-enumeration report fallback; it failed once, then passed after removing that fallback. All collision effects were confined to copied fixtures; no immutable baseline or real author source was written. Outputs are atomically replaced per file, not committed as one multi-file transaction; an I/O failure may leave a completed output alongside a missing later profile/report, while inputs remain protected.

### Exact validation commands and observations

All commands ran from this retopology workspace. Focused fixtures live only under `tools/pipeline_fixture_*` and use their verified workspace cleanup helper. Their runner required the same scoped sandbox escalation described in the historical report. Each RED log was recorded before its corresponding production fix; GREEN followed that fix. The approved executable was:

`C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe`

The actual focused command form was `& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' tools\pipeline_test.py <methods below> 2>&1 | Tee-Object -FilePath tools\<log below>`. The following table gives the exact method arguments and red/green output paths; only the filename differed between the two executions.

| Boundary | Exact method arguments | Logs under tools/ | Observed RED -> GREEN |
|---|---|---|---|
| F1 | `CanonicalTests.test_f1_triangle_storage_is_validated_before_casting_in_bridge_and_checker CanonicalTests.test_f1_unsigned_scalar_triangle_indices_remain_accepted` | `pipeline-review-r1-f1-red.log`, `pipeline-review-r1-f1-green.log` | 2 tests/8 failures -> 2 tests OK |
| F1 source | `CanonicalTests.test_f1_malformed_source_triangle_storage_is_not_trusted` | `pipeline-review-r1-f1-source-red.log`, `pipeline-review-r1-f1-source-green.log` | 1 failure -> 1 test OK |
| F2 | `CanonicalTests.test_f2_base_accessor_view_offsets_counts_and_strides_are_bounded CanonicalTests.test_f2_sparse_bounds_offsets_unsigned_order_and_range_are_validated CanonicalTests.test_f2_valid_interleaved_sparse_and_padded_matrix_accessors` | `pipeline-review-r1-f2-red.log`, `pipeline-review-r1-f2-green.log` | 15 failures/6 errors -> 3 tests OK |
| F3 | `CanonicalTests.test_f3_png_requires_supported_colour_and_legal_chunk_structure CanonicalTests.test_f3_rgb_rgba_8_and_16_bit_atlases_remain_decodable` | `pipeline-review-r1-f3-red.log`, `pipeline-review-r1-f3-green.log` | 7 failures -> 2 tests OK |
| F4 | `CanonicalTests.test_f4_unique_staging_preserves_source_named_as_legacy_temporary_file CanonicalTests.test_f4_external_buffers_and_images_are_protected_from_both_outputs CanonicalTests.test_f4_cli_report_collision_is_rejected_before_any_output_write CanonicalTests.test_f4_report_writes_protect_external_dependencies_and_checker_inputs CanonicalTests.test_f4_percent_encoded_external_image_resolves_without_mutation` | `pipeline-review-r1-f4-red.log`, `pipeline-review-r1-f4-green.log` | 17 failures/2 errors -> 5 tests OK |
| F4 dependency enumeration | `CanonicalTests.test_f4_report_does_not_drop_dependencies_when_another_uri_is_unsupported` | `pipeline-review-r1-f4-dependencies-red.log`, `pipeline-review-r1-f4-dependencies-green.log` | 1 failure -> 1 test OK |

After all fixes, ran one fresh owned Blender import/export and one complete scoped suite:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' --background --factory-startup --python tools\pipeline_blender_roundtrip.py 2>&1 | Tee-Object -FilePath tools\pipeline-review-r1-blender-roundtrip.log
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' -m unittest discover -s tools -p 'pipeline*_test.py' -v 2>&1 | Tee-Object -FilePath tools\pipeline-review-r1-full-suite.log
```

Blender completed both exports and quit normally, exit0. It retained the previously documented source-material sampler warning. Full suite: **33 tests in 24.657s, exit0, OK (expected failures=1)**. The expected failure remains the explicit baseline missing-morph acceptance proof; none of F1–F4 is waived or expected to fail. No subsequent production edits were made after this suite.

Fresh actual roundtrip checks preserved source nodes, 14-joint skin/order, exact IBMs and independent neutral transform. Symmetric position errors remain player 1.094525e-6m and foe 9.177003e-7m; canonical rest errors remain 7.060052e-7m and 4.454003e-7m. Fresh source/raw/canonical GLB hashes are unchanged from the historical table. The two roundtrip report JSON files now include the final bridge hash and pre-write immutable input hash map.

### Final review boundary and limitations

| Changed script | Final SHA256 |
|---|---|
| `tools/canonical_glb.py` | `734ff3ddbf55aba059ef998d4329a27b8421732960a038064005ae9011881667` |
| `tools/check_retopology_assets.py` | `e7577e725a7fc2c238faa9f6da19fa48fb2c7fea371f314f6e7741a989111bbe` |
| `tools/pipeline_test.py` | `5f74fb830a3369b838c24c59bf139f13032d17bfb7d76fa067d7a63eb00ff54d` |

`tools/pipeline-review-r1.manifest.json` records reviewed-before/final hashes, baseline hashes and evidence paths. Review-round diffs are `tools/pipeline_review_round1_after/*.patch`, against the preserved reviewed snapshot. The author audit helper, Blender helper and real roundtrip test script hashes remain unchanged. The old `pipeline-final-manifest.json` belongs to the initial boundary and is retained rather than silently updated.

The fixes close the supplied rejection/preservation probes and named variants; this checker is not a complete validator for every glTF extension or PNG ancillary feature. The original frame/rig/morph/tangent/PBR math, triangle/weight/contact limits and numerical locality tolerance are unchanged. PNG support is intentionally narrowed to channel-bearing RGB/RGBA atlases. Atomic replacement protects individual output files, not concurrent external mutation or a multi-output commit. Root still must assemble stable final role inputs, run the final checker with profiles, perform animation/visual/posed contact/performance acceptance, independently re-review this fix diff, and decide promotion. This worker did not rerun or modify reviewer-owned probes/evidence, replace game assets or claim current final character acceptance.
