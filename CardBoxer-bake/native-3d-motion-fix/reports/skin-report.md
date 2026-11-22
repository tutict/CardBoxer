# Native skin repair

Only the isolated project's `assets/3d/player-rigged.glb` and `foe-rigged.glb` skin bytes changed. The original baseline GLBs remain immutable rollback copies. No mesh surgery, bind-matrix changes, bone changes, hand remodelling, or pose-amplitude reduction was used.

## Diagnosis and bounded change

The exported meshes contain 2,035 player and 2,809 foe disconnected index components. Exact duplicate positions already have identical weights: **0 mismatched coincident-position groups** on both meshes. Welding or global weight smoothing would therefore add scope without fixing the observed spike.

The actual spike comes from isolated moving-surface vertices assigned entirely to the undriven `neutral_bone`: **28 player vertices / 15 unique positions**, and **18 foe vertices / 10 unique positions**. Player head-ribbon edges join rigid head vertices to static neutral vertices; a roughly 6 mm source edge extends by 0.410 m in sweep contact and 1.245 m in KO. Foe cape edges have the same missing-weight discontinuity; sweep adds up to 0.698 m.

The repair replaces only these 46 outliers. Donors come from the same connected surface, using exact-position adjacency across UV/normal splits, inverse-distance interpolation, and at most four normalized influences. Donor weights are frozen before interpolation. The player ribbon outliers are restricted to **head/neck** so residual arm influences in legacy donor weights cannot pull them with a punch. The foe cape outliers inherit their adjacent existing torso/thigh blend. All other vertices retain their original JOINTS/WEIGHTS bytes.

## Quantitative verification

Linear blend deformation uses the GLB node hierarchy, inverse-bind matrices, neutral-root transform, and **q_rest × q_delta** from the actual native combat table. Both roles were checked at all **97 authored keys across 19 clips**, including contact, recovery, hit, block, and KO poses. Ratios exclude source edges shorter than 5 mm; absolute added-length measures include every edge.

| Measure | Player before | Player after | Foe before | Foe after |
|---|---:|---:|---:|---:|
| Maximum added edge length, all keys | 1.244726 m | 0.187060 m | 0.698124 m | 0.186598 m |
| Maximum reduction | — | 85.0% | — | 73.3% |
| Distinct edges with > 10 cm added length | 336 | 300 | 153 | 132 |
| Vertices assigned to neutral | 28 | 0 | 18 | 0 |
| Changed vertices / total | — | 28 / 57,934 | — | 18 / 64,059 |
| Changed GLB bytes | — | 216 | — | 324 |
| Coincident-position weight disagreements | 0 | 0 | 0 | 0 |
| Maximum rest-position numerical error | 0.000000706 m | unchanged | 0.000000445 m | unchanged |

Remaining 0.1–0.19 m edge strain belongs to the original multi-bone limb/cloth skin and is independent of the neutral spikes. This patch deliberately leaves those weights unchanged. The fragmented source surface and absence of wrist/foot/finger bones limit what can be repaired without broader skin changes. Fresh native render QA must judge the residual joint appearance.

## Exact preservation and engine checks

The checker compares the full GLB byte arrays with a mask permitting **only JOINTS_0/WEIGHTS_0 accessor elements**. All other bytes are identical, including positions, normals, UVs, indices, material JSON, embedded images, bone names, node transforms, and inverse-bind matrices. JSON chunks and GLB lengths are identical. Unmodified vertices' joint and weight arrays are compared exactly. Changed weights are finite, nonnegative, normalized, and refer only to existing skin joints.

After headless `--editor --import`, a read-only Godot PackedScene/Skeleton3D probe confirms **14 bones per role**, unchanged bone names/order, parents, local rests, global rests, initial poses, model transform, and skeleton transform. `neutral_bone` remains present with its exact imported rest despite no visible vertex retaining a neutral influence.

Real logs and cached engine evidence:

- `logs/skin-reimport-engine.log`
- `logs/skin-reimport-stdout.log`
- `logs/skin-import-check-engine.log`
- `logs/skin-imported-rest.json`

Godot emitted its existing root-certificate-store warning and could not persist user editor settings outside the task sandbox. The two GLBs imported successfully and the independent cached-scene checks passed.

## Reproduction and rollback

`tools/check_native_skin.py --verify` was written and run before asset changes. It failed on the original GLBs because the large deformation defects did not improve. The final `--verify --godot <Godot executable>` run passes preservation, bounded scope, normalization, native-deformation improvement, coincident seam consistency, head-ribbon influence, and imported skeleton/rest checks.

Use the bundled workspace Python with NumPy:

```powershell
$skinPython = 'C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1118-904-0_26.1118.904.0_x64__3k8sg7r9htsxt/dependencies/python/python.exe'
& $skinPython 'native-3d-motion-fix/tools/repair_native_skin.py'        # read-only dry run
& $skinPython 'native-3d-motion-fix/tools/repair_native_skin.py' --write
& $skinPython 'native-3d-motion-fix/tools/check_native_skin.py' --verify --godot 'C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe'
```

Run Godot headless `--editor --import` with a real log file after writes. The repair is deterministic and always derives from baseline, preventing accumulated drift. Roll back by copying the two matching files from `baseline/assets/3d/` to `project/assets/3d/`, then reimport.

| GLB | Baseline rollback SHA-256 | Repaired SHA-256 |
|---|---|---|
| player | `80e5a1a03f446dd8a080e69524d4e78d97191fe56fcb30f86ed7e8c945fcab28` | `d4548f09c017ca65b1620cdabf6f9e4532bfbbddd7519d25da8eb3cdab6e2e5b` |
| foe | `0edcfe9e455f3c8c9deb7034397c815fd701130ed9a10c2e08800fff789cba88` | `08713ff745ab490396cd150f4e91617055c6a648cf85dd9fdcd28c532b76cd18` |

Assets are frozen for parent-task visual QA. No sibling game project files were changed.
