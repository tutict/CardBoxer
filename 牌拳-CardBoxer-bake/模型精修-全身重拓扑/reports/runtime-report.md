# Progressive hand runtime implementation and verification

The candidate samples two finite 0..1 hand controls on the existing Native V2
pose clock. The same open/half/closed coefficients drive four actual mesh morphs
and forearm-local contact sockets. Body pose equality, ordinary transition blends,
freeze, KO and reset include the hands; invalid controls are rejected before
display state changes. Foe's local canvas gain starts at .65/.55/.52 and will be
accepted only after a same-camera actual composite measurement.

The inherited implementation is in scripts/hand_shape.gd, native_motion.gd,
battle_presentation.gd and fighter_3d_layer.gd, with annotated
data/combat_motion_3d.json. The baseline is the immutable task baseline, not an
assumed prior design. reports/body-motion-contract.json compares the entire body
and phase payload after removing only hand_grip: all 1,502 keys remain exact.

Fresh evidence in this continuation:

- HAND SHAPE CHECK 151/151 passes. Log: logs/resume-hand-shape-engine.log.
- HAND BODY INVARIANCE CHECK: 24,034 checks, 1,502 integer/fractional samples
  covering all 19 clips and both roles, zero failures. Both root error and
  quaternion dot error are zero at printed precision. The comparator loads
  the immutable original NativeMotion implementation and original body data;
  this is independent of the new hand sampler. Log:
  logs/hand-body-invariance-tools-engine.log. Comparison-only harness remains
  under tools/check_hand_body.gd so installed game tests do not depend on a
  sibling baseline directory.
- Initial HAND ASSET CHECK is genuinely RED at 5/10 while the candidate still
  contains legacy GLBs and no canonical model profile. Log:
  logs/resume-hand-asset-engine.log. This does not accept new assets.

Historical initial missing-hand RED/GREEN logs are retained under logs/ and
recorded in progress.md. They are provenance, not substitutes for fresh final
asset/socket checks. The Windows certificate-store warning is environmental;
no script/runtime error appeared in the two passing focused checks.

Final imported socket/morph, same-view foe brightness, freeze/event integration,
both modes, geometric/visual and performance acceptance remains pending canonical
author outputs. Root owns these gates and publication. No main-game files have
been modified in this continuation at this report boundary.
