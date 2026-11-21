# Task 1 independent pipeline review

Reviewed 2026-11-20. Scope is the canonical export bridge, acceptance checker, and pipeline evidence. Read `briefs/pipeline.md` first, followed by `spec.md`, `contracts.md`, the pipeline report, and the supplied initial patch package. No usable source Git history exists: BASE is immutable installed Natural V2; HEAD is `reports/reviews/pipeline-initial.patch.manifest.json`. All six current implementation/test files match the packaged SHA256 boundary. This review made no Git operations and changed no implementation, authoring, baseline, runtime, or main-game files.

**Task spec verdict: PARTIAL — changes required.** Canonical rig/frame transfer and actual unedited source compatibility have credible evidence, but the delivery checker demonstrably accepts malformed new inputs.

**Task implementation verdict: REQUEST CHANGES.** Four P2 findings below affect final rejection reliability or input preservation. The bridge remains useful for scoped assembly/roundtrip diagnostics; this is not approval to treat its checker as a complete final promotion gate.

Integrated character/runtime readiness remains with root and authors. The recorded author snapshots were correctly rejected inputs; their missing tangents, player AO reference, and tiny outside-hand NORMAL residues are not additional pipeline implementation findings. No conclusion about the final concurrently refined author files, visual improvements, Godot behavior, or installation follows from this review.

## Four independent axes

| Axis | Assessment | Basis |
|---|---|---|
| Spec | Partial; changes required | Exact API, original nodes/scenes/14-joint skin/IBMs, neutral declaration, joint remap, mesh-frame transfer, socket conversion, triangle budget, PBR references, morph names/locality are implemented. F1–F3 leave invalid author artifacts accepted by the final checker; F4 leaves input protection incomplete. |
| Standards | Workflow conforms; input-preservation invariant violated | Supplied ownership/execution rules are the applicable standards (`contracts.md:5`, `contracts.md:7`, `contracts.md:69`, `briefs/pipeline.md:27`). The packaged helper is tools-only, no Godot launch or user-process termination appears, and baseline hashes remain unchanged. F4 violates the API's source-preservation invariant for colliding caller paths. No separate applicable code-style document was found; stylistic preferences are not graded as defects. |
| Implementation Quality | Request changes, four P2 findings | The transform/math design is sound for the stated canonical assets and direction endpoints; rejection logic has independently reproduced false positives, and output staging can consume an input. Each finding identifies a concrete trigger and corrective boundary. |
| Verification & Evidence | Strong positive compatibility evidence; incomplete rejection coverage | The recorded 19-test run, real Blender export log, provenance, and both canonical roundtrip reports agree and match current hashes. Six focused probes exposed cases absent from that suite. The claim that malformed input fails closed and inputs cannot be overwritten is therefore broader than the evidence. No full suite or Blender roundtrip was rerun. |

Severity is by effect with preconditions: these are P2 because they require malformed author files or colliding caller paths. There is no evidence of current frozen-source corruption, rig drift, or a broken currently accepted final game asset.

## Findings

### F1 — [P2] Validate triangle accessor storage before casting/flattening

Location: `tools/check_retopology_assets.py:102` (cast/flatten), `tools/check_retopology_assets.py:105` (only post-cast bounds/count check); bridge propagation at `tools/canonical_glb.py:238` and `tools/canonical_glb.py:276`.

The checker converts any triangle accessor to integers and flattens it before checking. A FLOAT SCALAR payload `[0.25, 1.25, …, 8.25]` becomes the valid triangle sequence `[0, 1, …, 8]`. A UINT16 VEC3 accessor with three records likewise becomes nine apparently valid indices. Both mutated candidates returned `ok: true`, no errors, three triangles. glTF triangle indices require unnormalized unsigned SCALAR storage; these accepted files violate the runtime container contract and can fail import or be interpreted differently by a compliant consumer. For positive-determinant frames the bridge retains the invalid raw index accessor; for reflection it can silently coerce it through the UINT32 writer. The report's unsigned-index rejection wording at `reports/pipeline-report.md:18` only has supporting JOINTS_0 format tests, not triangle-index protection.

Axes: Spec, Implementation Quality, Verification & Evidence. Relevant requirements: runtime GLB/single surface and triangle budget (`spec.md:18`, `briefs/pipeline.md:16`). Corrective boundary: require SCALAR, componentType 5121/5123/5125, normalized=false, correct element count and valid range before conversion; use the same check in bridge and final checker. Add focused rejection cases for FLOAT/fractional, vector, and normalized index accessors.

Evidence: `reports/reviews/pipeline-characterization/results.json`, probes `fractional_float_triangle_indices` and `vec3_triangle_indices`.

### F2 — [P2] Bound accessors to their declared bufferView

Location: `tools/canonical_glb.py:59`–`tools/canonical_glb.py:61`; final checker entry at `tools/check_retopology_assets.py:100`.

`GLB.accessor` constructs a NumPy array over the complete buffer with absolute offset/stride, ignoring the enclosing bufferView's declared byteLength. Shrinking the nine-vertex POSITION view from 108 bytes to four bytes left its payload in the backing buffer; the final checker still read all 108 bytes and returned `ok: true`, no errors. Its calculations consequently validate bytes outside the declared view. This is an invalid GLB and a consumer may reject or read a different extent. Exception-to-error handling does not help because NumPy's larger-buffer read succeeds. The bridge also uses this reader and retains old raw views/accessors when appending canonical data, so canonical repacking is not a substitute for validation.

Axes: Spec, Implementation Quality, Verification & Evidence. Relevant gate statement: `reports/pipeline-report.md:22` and `reports/pipeline-report.md:125` claim malformed accessor data fails closed. Corrective boundary: validate integer nonnegative offsets/counts, valid stride/alignment, and `(count-1)*stride + element_size + accessor_offset <= view.byteLength`, with the entire view bounded by its buffer; handle sparse index/value extents similarly before reading. Reject the short-view fixture rather than letting backing-buffer size make it acceptable.

Evidence: `reports/reviews/pipeline-characterization/results.json`, probe `position_accessor_crosses_view_boundary`.

### F3 — [P2] PNG scanline checks do not establish valid indexed PNG encoding

Location: `tools/check_retopology_assets.py:27`–`tools/check_retopology_assets.py:39`; acceptance use at `tools/check_retopology_assets.py:197`.

The PNG parser permits color type 3 but never requires or validates its mandatory PLTE chunk. A 4096×4096 indexed PNG containing IHDR, a complete correctly filtered zlib scanline payload, valid CRCs, and IEND, but no palette, replaced the candidate's base-color image and still produced `ok: true`, no errors, all three images reported 4096². There is no RGB value mapping for its indices; it is invalid PNG, not merely a poor bake. This can reach texture import despite the final material gate and contradicts the legal-encoding claim at `reports/pipeline-report.md:24`.

Axes: Spec, Implementation Quality, Verification & Evidence. Requirement: three actual 4K PNG PBR images (`spec.md:19`, `briefs/pipeline.md:16`). Corrective boundary: either deliberately restrict these atlases to supported RGB/RGBA encodings, or validate required palette/chunk ordering and palette constraints for indexed PNGs. Keep visual bake judgment as the separate root gate; this finding concerns structural decodability.

Evidence: `reports/reviews/pipeline-characterization/results.json`, probe `indexed_png_missing_required_palette`.

### F4 — [P2] Include staging files and external raw dependencies in collision protection

Location: `tools/canonical_glb.py:175`–`tools/canonical_glb.py:180` (guard), `tools/canonical_glb.py:159` (predictable staging name), `tools/canonical_glb.py:251` and `tools/canonical_glb.py:267` (read raw image, then write output).

Direct equality protection covers the five named API paths but excludes the writer's `<output>.tmp` and external raw image/buffer paths. Two isolated calls showed the consequences. Passing a copied source at `collision-output.glb.tmp` with output `collision-output.glb` passed the guard; `Builder.write` overwrote and then moved that source, leaving the supplied source absent, an output present, and a later provenance FileNotFoundError. Separately, choosing an external raw PNG as output successfully returned from canonicalize after replacing that PNG with a GLB (magic `glTF`). Neither case changes the protected real baseline directory in this review, but valid caller-supplied input resources are lost and the API's input-immutability guarantee at `reports/pipeline-report.md:18` is false for these paths.

Axes: Spec, Standards, Implementation Quality, Verification & Evidence. Standards/contract: `contracts.md:16`, `contracts.md:69` (“source never overwritten”), and the tools-only/no-baseline-write boundary at `briefs/pipeline.md:27`. Corrective boundary: enumerate resolved file inputs including external buffer/image dependencies, reject collisions with both outputs and any scratch/report paths, and use an exclusively created unique staging file. Check collisions before any write and compute immutable-input provenance before mutation; do not silently permit a failed report after consuming an input.

Evidence: `reports/reviews/pipeline-characterization/results.json`, probes `source_is_output_temporary_path` and `output_overwrites_raw_external_image`.

## Positive review conclusions and practical limits

The exact API is present at `tools/canonical_glb.py:173`. The bridge uses `inverse(source_mesh_global) @ raw_mesh_global` (`tools/canonical_glb.py:210`), remaps by exact joint names, restores source nodes and skins, and copies IBM numeric payloads (`tools/canonical_glb.py:241`). Normals use inverse transpose; tangents use the linear transform, reprojection, normalization and determinant sign; morph NORMAL/TANGENT endpoints are recomputed as direction deltas (`tools/canonical_glb.py:214`, `tools/canonical_glb.py:221`, `tools/canonical_glb.py:228`). No contrary concrete math defect was found. The fixture covers different nonidentity mesh frames, reordered raw joints, and omitted unused neutral. Real source/raw frames happen to be identity; that is recorded rather than generalized.

The final node equality gate covers canonical hierarchy, local TRS/matrices, mesh/skeleton transforms, node morph defaults and independent neutral transform; joint order, skin metadata, scenes and IBM equality have separate gates (`tools/check_retopology_assets.py:88`–`tools/check_retopology_assets.py:94`). Extra nonzero weights, negative weights, neutral influence and JOINTS_0 storage checks are present. Four morph names, zero defaults, per-target shape/finiteness, nonempty POSITION and own-hand envelope checks are present. The material gate requires three image references, UV0, ORM AO reuse, and an orthonormal tangent basis. Those positive gates do not negate F1–F3.

The corrected hand envelope at `tools/check_retopology_assets.py:147` uses original own-forearm weighted geometry and bounded distal local XYZ, replacing the disproved upperarm-length heuristic. It prevents the named arbitrary-remote-weighted-vertex acceptance and differing-arm-proportion rejection addressed in the report/tests. It remains an envelope rather than semantic hand segmentation; there is insufficient contrary evidence to grade that declared limitation as a new defect. In-hand stationary-vertex normal changes can be real hand shading changes; outside-hand residue around 2.55e-8 in recorded rejected snapshots is numerically tiny and was not accepted by loosening the checker. Own-hand topology, normal-map orientation/bake correspondence, intermediate fist quality, and meaningful sockets still need root's visual review. Tangent orthonormality alone does not prove the UV/bake relationship.

Socket conversion `(x,y,z)->(x,z,-y)` followed by inverse original forearm global transform is correct (`tools/canonical_glb.py:258`–`tools/canonical_glb.py:264`). The checker tests point-to-triangle distance at open/half/closed (`tools/check_retopology_assets.py:218`), and explicitly warns when profile is omitted (`tools/check_retopology_assets.py:229`). Root must supply the final profile, test .25/.75 interpolation and posed contact/sole behavior, and merge the role profiles; canonicalize alone is intentionally not final author acceptance.

## Verification and provenance assessment

The actual Blender helper imports the immutable sources, selects only the skinned body mesh and armature, and exports with skins/morphs, no animations/apply, Y-up (`tools/pipeline_blender_roundtrip.py:14`, `tools/pipeline_blender_roundtrip.py:22`–`tools/pipeline_blender_roundtrip.py:30`). It performs no authored mesh/armature changes. The log records both actual exports, the completion marker and Blender 5.2.0 LTS build `fbe6228777e7` before normal exit (`tools/pipeline-blender-roundtrip.log:21`, `tools/pipeline-blender-roundtrip.log:97`, `tools/pipeline-blender-roundtrip.log:99`). The Icosphere-selection correction selects the intended mesh; it does not invalidate unchanged-source provenance.

The source-material warnings at `tools/pipeline-blender-roundtrip.log:8` and `tools/pipeline-blender-roundtrip.log:17` mean the exporter chooses the first sampler configuration when multiple texture nodes contribute. That limits claims of exact material/sampler roundtrip fidelity, which the compatibility task does not claim. It does not invalidate measured rig/rest geometry compatibility or final new-atlas validation. The recorded sandbox access failure was rerun outside the sandbox in the existing evidence; it is an environment issue, not a hidden passing compatibility result.

The real comparison handles seam splits with symmetric nearest position distance (`tools/pipeline_roundtrip_test.py:17`, `tools/pipeline_roundtrip_test.py:49`). It is appropriate to the required unchanged-source vertex-position check, not a watertightness or connectivity proof. Recorded maxima are player 1.094525e-6m and foe 9.177003e-7m; canonical rest errors are 7.060052e-7m and 4.454003e-7m. Both are below 1e-5m. Current source, actual raw and canonical roundtrip hashes all match their provenance/reports, and report bridge hashes match the reviewed implementation. The reports mark diagnostic sockets explicitly.

`tools/pipeline-final-suite.log:24` records 19 tests in 13.629s and `tools/pipeline-final-suite.log:26` records OK with one expected baseline missing-morph failure. This review acknowledges that recorded run and does not claim a fresh rerun. Existing regressions are meaningful, but none exercise the F1–F4 cases; the readiness/fail-closed claims should be revised until fixes and focused regressions land.

Independent command executed once successfully after correcting the review script's UTF-8 manifest read:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' 'reports\reviews\pipeline-characterization\probe.py'
```

Exit 0. Control candidate passed. Four malformed candidates passed incorrectly; two collision probes observed the input effects described above. The probe only imports fixture builders and validators, writes review-owned copied inputs/results, and hashes existing package/provenance artifacts. It does not run the 19-test suite, launch Blender/Godot, or consume real author inputs. Reproducer and full machine-readable results remain in `reports/reviews/pipeline-characterization/`.

After F1–F4 are addressed, root still owns final stable-input canonicalization/checking, all19 clips/both facings, open/.25/.5/.75/closed visual hands, actual posed sockets/soles <=.02m, normal/slow previews, both modes, event/freeze/reset/timing, performance and guarded promotion. Those integrated gates are separate from this scoped Task 1 review.
