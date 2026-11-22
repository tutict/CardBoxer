# Final native 3D combat code review

Review date: 2026-11-20. Scope: current isolated `project/` production scripts against immutable `baseline/`, plus the approved `plan.md` and `contracts.md`. This is a manual read-only review. The only file written by this review is this report; no sources, assets, installation, or commits were changed, and no test suites were rerun.

## Conclusion

No new actionable functional finding was identified in the inspected changes. Both P2 findings from `code-review.md` are resolved in the current production source.

### Resolved: signed retreat gait

`fighter.gd:348` records the sign of actual traveled X relative to facing. The read-only snapshot retains it at `fighter.gd:196`; `battle_presentation.gd` reverses the cyclic phase for retreat and includes the sign in walk transition identity. A direction reversal therefore begins from the displayed stride and blends toward the reversed gait, rather than snapping between two phases. Logical speed, clamp, facing, collision, legacy 2D gait and position updates remain on their existing paths.

The existing transition regression log proves both roles and both facing signs, exact logical displacement, and forward/retreat pose distinction. The current test also contains focused walking-reversal blend assertions. The historical `integration-spacing-transition-green.log` is 43/43 and predates those additional assertions; it is not evidence that the newest assertions ran.

### Resolved: normal 0.06-second pose transitions

`battle_presentation.gd` now stores the displayed outgoing pose and a separate transition clock. Ordinary clip/state/action/direction changes use shortest-path quaternion interpolation and matching root interpolation over `BLEND_S=0.06`. Replacing an unfinished transition starts from the pose actually displayed. Hit, block, held contact and KO bypass the blend immediately. Pause, global hitstop, local hitstop and the explicit taikou contact hold stop transition time; reset clears outgoing poses, identities and transition clocks.

Existing focused transition evidence checks start, midpoint, completion, idle/walk-to-action changes, pause/global/local freeze, reset and immediate reaction/contact priority. Source inspection confirms the layer applies the controller's resulting pose without adding a second transition or the retired stance bias.

## Remaining functional review

- **Event ordering:** rule settlement remains in the existing hit/taikou paths. Deferred native taikou cues retain round/action identity and emit once when the visual clock crosses 0.48 seconds. Crossing and hold overshoot are retained. Cue emission calls effects only; it does not repeat damage, card signals, meter, rage or gameplay RNG.
- **Late wave/new action:** release and projectile collision use separate source kinds. The projectile stores its originating action identity; collision starts only the victim reaction and cannot restore an older attacker latch. Fatal late collisions capture the winner's currently playing action before `freeze()`, then finish its remaining phases independently.
- **Fatal exchange:** taikou retains its exchange across arena round-over, reaches contact, holds, then advances a 0.45-second terminal KO to frame27. Realtime terminal victim/winner clocks consume their saved local hold independently of stopped Fighter clocks. Projectiles stop settling after round-over. Round reset clears events, clocks, effects, global hold and slow motion.
- **Calibration and physical rules:** taikou calibration predicts the authored hand and target head/chest from the real imported rig/camera. Its extra approach modifies only `canvas_shift`; logical spawns, reach, collision and damage are preserved. The lower-leg approach overlay leaves authored hands/root intact and vanishes at exact contact. Deferred generic effects and rhythm sparks share the calibrated contact point. Native shift/tilt changes invalidate the Fighter shadow draw even when Fighter ticks are stopped.
- **Transforms/facing:** driver composition remains `q_rest * q_delta`, with unchanged rest translations/scales and one hips root offset. The neutral import bone is not written. `pose_global_transforms()` computes a separate hierarchy without mutating live bones; `anchor_offset()` accounts for model facing, imported skeleton transform, camera, draw scale, foe scale, optional flip and canvas tilt. Facing rotation starts from the imported model transform and does not accumulate or mirror local anatomical quaternions.
- **Data fallback:** native data is validated completely before availability: required roles/clips, phase/card compatibility, contact endpoint, key coverage/order, finite numeric values, unit quaternions, card/reaction closure and loop closure. Native-load failure leaves the created 2D Fighters active. Both layers must initialize before both 3D overrides activate; layer setup failure retains visible 2D Fighters. Legacy motion dictionaries and the shipped compatible GLB layout remain existing setup assumptions; arbitrary malformed legacy schemas were not fault-injected by this review.
- **Launch path:** the new realtime 3D launcher sets the selected battle mode and delegates to the existing 3D launcher. The environment override is read before Arena match setup. The project configuration has no baseline diff.

## Evidence and limits

Inspected current production source, focused tests and actual saved results. Existing final spatial logs show controller44/44, imported rig124 checks, normal-spawn contact70/70, shadow redraw pass, both-mode live integration14/14, and native motion1,502 samples with maximum actual support error0.012953m. Legacy rule/flow/rage/rhythm/motion/skin/portrait/redraw checks have passing final spatial logs. These are existing run results, not runs performed by this review.

Skin and actual-sole preservation/measurement reports were read; their numerical procedures were not independently rerun here. Pure projected contact alignment does not certify glove volume, temporary approach-foot support, mesh overlap, clipping or final rendered composition. Final Compatibility-renderer capture and installation remain with the parent task. The older full visual QA images are not treated as final acceptance of the subsequently adjusted poses/camera/skins.

Reviewed script SHA-256 values:

| Script | SHA-256 |
|---|---|
| arena.gd | `ace6f65a55892e445526cc553cfc8bab0574d217afb8ab664708731f5767e368` |
| fighter.gd | `ce00118908263055d20980736442f70271c7a8b887e8e0d2b99d5fdaf1873280` |
| battle_presentation.gd | `a5bfa5ed637264a2e67ec07a73e479b28774facfa3e755da077e6e556661f665` |
| native_motion.gd | `b7baa4b0ea8fe35c61f609fb3b9c889409425760ff3a9219ab3dc11ce3805bce` |
| rig_driver.gd | `f9cb3beb60d54e06f2609ce8aa04ee47e4aa4b2cff6a6b55682a6921cfa98113` |
| fighter_3d_layer.gd | `982f677850c19d7bf1c822043c18cacd31ec69237f0deaabc91543def4fc22e7` |
