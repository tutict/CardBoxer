# Final natural-flow V2 visual review

Reviewed the frozen candidate in `project/`; motion SHA256
`083c84e3e24bdb4bea6d3e4b92855322caea97d675cae19a06df36acefd5a703`.
Result: **PASS for complete rendered silhouettes, authored motion direction and
continuous isolated presentation cycles. Root completed the separate V2 normal-spawn
full-match acceptance described below.** No project source, main checkout, GLB,
skin, geometry, material or gameplay file was edited by this reviewer.

## Fresh real-render evidence

Godot4.5 Windows OpenGL Compatibility used the NVIDIA GeForce RTX5080 Laptop
GPU, with a real hidden window. The capture manifests record the candidate
source hashes. `shots/natural-v2-final/` has **3,004 transparent720x680 PNGs**:
all19 clips, both roles and both relative facings, including every dense
half-frame key. `natural-v2-final-framing.json` passes every image with four-pixel
padding; zero empty/clipped images. Ten phase boards in
`natural-v2-visual-boards/all19-facing*-page*.png` were visually examined across
all19 clips and both sides. No new giant skin spikes, stretched triangles,
truncated limbs or explosive pose changes were observed in those silhouettes.

`shots/natural-v2-final-timeline/` has830 fresh PNGs produced by the tools-only
`natural_preview_capture_v2.gd`. It calls the candidate's actual
`Presentation.advance(1/60)` and `sample()` for each role independently, using
the1.12s taikou attack and0.24s impact hold. The280px approach contribution also
enables the candidate's actual forward/recovery leg overlay. Each clip includes
guard, load, contact hold, return and final guard. Timeline framing also passes
all830 images. Regular-time filmstrips for the five attacks were reviewed.

Three production-state-machine real-render scenarios were captured under
`shots/natural-v2-final-live/`: player cross, foe sweep and taikou-player. The
summary and `natural-v2-final-live-timing.json` pass with no failures. The cross
hit samples frame9 exactly; taikou contact appears for16 recorded ticks. Their
940 transparent role images have zero clipped/empty images. Full arena samples
and honest10fps GIFs are in `natural-v2-visual-boards/`.

**These three harness setups use85px separation**, which visibly overlaps the
models. They establish production timing/render continuity, not normal-spawn
contact spacing. Foe sweep records zero hit events and is motion-only evidence.
The root's normal match starts at430/850px and owns the final approach/return
and contact judgment. The close-distance scenes show no new vertical body jump
or severe detached/ floating limb; they cannot establish natural long-distance
foot sliding by themselves.

## Concrete comparison with V1

The actual `versions/v1/preview.gif` was sampled across its saved duration, and
its companion PNG was inspected. The historical GIF has152 frames,7.6s total,
720x360 size and a20fps label. The new preview uses different production visual
timing, so playback speed alone is not used as proof of improvement.

- Guard: elbows are now bent and near the body instead of the previous broad
  opening pose. The player wrists sit near the cheek; the foe uses its own
  asymmetric chain proportions. This reads more protective at guard endpoints.
- Jab: the hand stays near guard through early loading instead of making the
  V1 large backward chamber; the short forward strike and early hand return
  remain readable. The rear arm stays protected.
- Cross: pelvis/chest turn is visibly separated from the arm extension; return
  follows several changing body/arm poses rather than an obvious complete-body
  snap. The rear-side view exposes this turn more clearly than the front view.
- Sweep: the body sinks first, the striking boot traces a low lateral path and
  the contact leg is much straighter. V1 reads more like a raised bent-knee kick.
  The support leg stays underneath the body, with no visible ankle explosion.
- Uppercut: the lower chamber, body dip and rising hand arc are clear before the
  contact hold. The hand descends before the whole torso has fully settled.
- Wave: hands gather near the torso while weight loads, then push forward and
  return to cheek guard. It no longer reads as only the contact arm pose changing.
- Across the five continuous cycles, no obvious pause at arbitrary intermediate
  keys or abrupt final guard reset was observed. The intentional contact hold
  is preserved. The native author/runtime reports provide the separate numerical
  C1/interpolation and imported-sole measurements.

Remaining limits: the original rigid player hand mesh still has visibly open
fingers. Forearm roll helps its silhouette but cannot make a closed boxing fist.
The foe's dark armor and cape obscure some wrist/leg motion. Gait is restrained;
the isolated role viewport keeps each actor centered and omits canvas translation,
so use the normal-spawn full match for ground-relative sliding/step readability.
Cloth remains bound to the existing coarse rig and has no new secondary physics.

## Deliverables and timing

- `natural-preview-v2.gif`:880x547, **6.920s** endless loop, five sequential full
  cycles, both roles.415 source60Hz frames use centisecond10/20ms scheduling.
- `natural-preview-v2-slow.gif`:same cycles/size, **20.750s**,50ms per source
  frame, labeled3x slow motion. No arbitrary extra hold is added by the exporter.
- `natural-preview-v2.png`: static guard and five contact silhouettes.
- `natural-preview-v2-metadata.json`: source hashes, crop/tile dimensions,
  saved GIF timing and all capture/live image counts.

All frames share one constant padded crop measured from the union of the source
silhouettes, with dynamically sized440x473 tiles; there is no tile overlap or
body crop. GIF compression combines identical frames, including the legitimate
contact holds:335 encoded frames preserve the entire source timeline. Thus the
encoded normal GIF also contains merged30/40/260/270ms delays; the slow GIF has
merged100/800ms delays. These are repeated images, not missing motion samples.

Capture commands are reproducible through existing `launch_native_qa.ps1`
(`capture`, `all`, `both`, name`natural-v2-final`; `live-render`, stride1, the three
quoted scenario names, name`natural-v2-final-live`). Timeline and package helpers
are tools-only files. Real renderer processes exited0 without parse/runtime
errors; the host's known root-certificate-store diagnostic remains in their logs.

No commits, subagents or production edits. Safe to continue root's fresh tests,
normal-spawn full match and guarded incremental installation after that check.

## Root normal-spawn acceptance, after reviewer handoff

Root captured frozen V2 through `tools/launch_normal_match.ps1`, using an absolute
writable engine log and a real hidden Compatibility renderer. The production arena
ran to `match_over` after **2,629 frames**, producing **121 screenshots** with normal
430/850px spawns. Every recorded logical position stayed at 430/850px. The process
exited 0, with no script errors or access violation; only the known certificate-store
diagnostic appeared. The old `final-normal-match` remains V1 evidence.

The new evidence is `shots/natural-v2-normal-match/match.json` and
`reports/natural-v2-normal-match-review/`. Root inspected both exchange filmstrips,
including the .480s contacts, early hand recovery, backward shuffle and final guard
at approximately 1.12s. Hands and torso recover through several changing poses;
the actor stays near contact briefly before retreating, and both return to their
original displayed places. No abrupt whole-body reset, new vertical jump or severe
detached limb was observed. Dark armor partially conceals the foe's footwork, and
the gait remains restrained on the original coarse rig. This satisfies the final
normal-spawn check without claiming perfect horizontal foot locking.

`review.json` records the selected source frames and the reviewed motion hash
`083c84e3e24bdb4bea6d3e4b92855322caea97d675cae19a06df36acefd5a703`.

Root handoff: use the existing `project/tests/native_match_capture.gd`, with
`NATIVE_MATCH_CONTINUOUS=1`, for `shots/natural-v2-normal-match/`. This V2 normal
match directory did not yet exist at review completion; the older
`shots/final-normal-match/` is V1 evidence. Select first-round resolve samples by
`match.json`'s `exchange_time`:0,.10,.20,.35,.48(contact/hold),.56(retreat start),
.65,.80,1.0 and1.12(final guard). Especially inspect hand return while the torso
stays forward at.48–.56, and the subsequent reverse gait through1.12.

The root reported a repeated Godot access-violation popup and identified it as
the existing log-path issue. This reviewer made no production workaround and
did not reproduce that popup in these captures. Every launch above used an
actual absolute writable `--log-file`; all three final render processes exited0.
No additional Godot probe was added or launched after the root's stop instruction.
