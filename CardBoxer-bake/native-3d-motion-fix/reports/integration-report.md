# Battle presentation integration report

Implemented only the isolated task project's `scripts/arena.gd`, `scripts/fighter.gd`, `scripts/battle_presentation.gd` and integration-owned tests. The sibling game was not edited; no commits, installs, or destructive commands were issued.

## Result

- Fighter exposes read-only `presentation_snapshot()` with the contracted state, card/action identity, phase clocks, reaction clocks, local hitstop, facing, movement/distance phase, visual walk blend, guarding/dodging/super and HP. Action sequence increments for both logical and visual actions. `freeze()` saves the outgoing action snapshot before clearing rule state. New rounds clear action identity, hold, movement blend, shifts and tilt.
- Arena reads `CARD_BOXER_BATTLE_MODE=taikou|realtime` at startup, retaining taikou as default and the existing 3D toggle. Missing or invalid native motion keeps the original 2D fighters visible with a clear error. Native sampling is shared across both roles; arena supplies fighter position plus sampled canvas shift, and the root-owned layer consumes pose/facing/tilt.
- Taikou still settles HP, rage and result in `_resolve_taikou()`. Immediate hit signals are captured into deferred cue payloads, then emitted visually once at contact. No hit, signal, meter or RNG is replayed by cues. The premature 0.07s hold is removed only from this native taikou cue path.
- Taikou contact at 0.48s clamps to the authored final active frame; attack sampling maps source frames piecewise before/after contact through 1.12s. The existing global 0.24s pause freezes contact. Both crossing overshoot and hold overshoot are carried into the next visual advance. Reveal remains 1.5s and logical resolve remains 1.9s.
- Realtime uses existing Fighter phase progress and Defs timing; active-last-tick rules and positional movement are retained. Impact starts at native reaction frame zero. Actual local/global hitstop controls contact latches. Wave release creates a one-frame peak latch, while later projectile impact affects only the victim and retains the original projectile action identity.
- Fatal impacts capture independent KO and winner recovery clocks before gameplay freeze. Fatal taikou continues to contact after `round_phase=over`; realtime terminal recovery also preserves a new action if an older wave arrives fatally. KO lasts 0.45s, holds its final frame, and the winner returns to guard. Projectiles stop settling immediately after over.
- Spark, floating text and shake now use a dedicated `RandomNumberGenerator`, isolated from gameplay RNG. Old mixed-RNG seed replay is intentionally outside compatibility scope.
- Pause freezes controller time; slow motion uses the supplied world delta; hitstop advances hold time only. Duplicate and stale exchange/impact identities are rejected. Reset clears controller queues, terminal clips, reaction/latch state, accumulated visual time and old action IDs.

Runtime interfaces added beyond the required contract: `cue_ready(impact)` signal; `capture_terminal(snapshots)` used by Arena before realtime freeze; public read-only-by-convention controller diagnostics `exchange`, `exchange_time`, `contact_emitted`; arena diagnostics `presentation`, `native_library`, `last_visuals`, `_presentation_context()`, `_native_active()`. No production test setup hooks were added.

## Verification

Engine command pattern: `Godot_v4.5-stable_win64_console.exe --headless --path project --log-file <real reports path> --script res://tests/<test>.gd`. Every final run below exited 0; no GDScript errors occurred.

| Test | Final result | Log |
|---|---:|---|
| battle_presentation_check | 38/38 | `integration-final-battle_presentation_check.log` |
| battle_integration_check, native 3D, startup taikou | 14/14 | `integration-final-live-taikou.log` |
| battle_integration_check, native 3D, startup realtime | 14/14 | `integration-final-live-realtime.log` |
| taikou_flow_check | 51/51 | `integration-final-taikou_flow_check.log` |
| taikou_rules_check | 90/90 | `integration-final-taikou_rules_check.log` |
| taikou_rage_check | 1482/1482 | `integration-final-taikou_rage_check.log` |
| battle_rhythm_check | 62/62 | `integration-final-battle_rhythm_check.log` |
| battle_motion_p0_check | 93/93 | `integration-final-battle_motion_p0_check.log` |
| engine_opt_check | 37/37 | `integration-final-engine_opt_check.log` |
| fighter_skin_check | 70 checks, no failure | `integration-final-fighter_skin_check.log` |
| motion_check | 228 frames, 5016 value comparisons, no failure | `integration-final-motion_check.log` |
| portrait_wiring_check | 157/157 | `integration-final-portrait_wiring_check.log` |
| redraw_gate_check | 72/72 | `integration-final-redraw_gate_check.log` |
| native_motion_check, author-owned | 1502 samples, no failure; max support error 0.015801m | `integration-final-native_motion_check.log` |
| native_rig_check, root-owned | 116 checks, no failure | `integration-final-native_rig_check.log` |

Pure controller coverage includes .479/.480/.481 boundaries, 30/60/120fps crossing, cue deduplication, immediate draw reactions, terminal KO completion/reset, pause, supplied slow-motion delta, distance-based walking at walls, stale realtime reaction rejection, wave release versus projectile collision, duplicate exchange identity, stale round events, and preserved timing remainder.

Live integration uses real production card input/ticks/signals and native imported layers. It verifies immediate fatal taikou HP settlement without early effects, fatal attack continuing under over, one contact cue/hold, KO ending at frame27, reset cleanup, release at wave frame17, late nonfatal projectile preserving a new jab, and late fatal projectile preserving/recovering that new jab before KO hold.

## Red/green evidence and encountered issues

- `integration-red.log`: expected missing snapshot/controller failures, 0/2.
- `integration-arena-red.log`: expected startup mode and gameplay-RNG isolation failures, 0/2. An initial test type inference error was corrected before the valid red run; the valid log replaced it.
- `integration-release-terminal-red.log`: expected release and terminal failures, 28/33. The author was still completing full clips at the start of this run; current full data and controller fixes later passed.
- `integration-wall-react-red.log`: wall blend and stale reaction failures, 33/35; both fixed.
- `integration-event-red.log`: duplicate exchange cue failure, 36/37; fixed by identity rejection.
- `integration-remainder-red.log`: lost hold overshoot failure, 37/38; fixed by carrying the remainder.
- `integration-terminal-projectile-red.log`: fatal late wave erased current jab and winner guard, 12/14; fixed by terminal action capture.
- First full legacy suite had one source-shape false positive in engine_opt_check: substring `rng.randf_range` matched the new `_visual_rng.randf_range`, although the old backdrop code remained retired. Renaming the independent visual field `_visual_random` resolved it without changing the old test; final result 37/37.
- Initial live integration setup inside SceneTree `_initialize()` produced camera `look_at` errors because the root was not yet inside its tree, and could invoke Arena `_ready()` twice. The integration test now begins with deferred `_run()`; final native runs are free of those errors.

## Limits / coordination

Godot emits `Failed to read the root certificate store` on this host on almost every headless test, including unchanged rule tests. This engine environment warning is preserved in real logs; it does not affect these local tests, and no network behavior is being validated.

Headless tests verify clocks, cues, rule preservation, native pose sampling and imported rig data. They do not establish final rendered image quality. The QA agent owns real Compatibility-renderer capture and full fixed-deck gameplay traces; its report is separate. The arena retains the prior raw-table sync function under the unused name `_sync_3d_layer_legacy()` for historical diagnostics; the active runtime sync calls only native `apply_visual()`.

## 2026-11-20 code review follow-up

Addressed both P2 findings in `code-review.md` and the requested generic native impact-anchor inspection:

- Snapshot now includes `walk_direction`, derived from signed **actual** traveled X distance relative to current facing. A retreat reverses native gait phase. Both roles and both facing signs are tested, and their logical displacement remains exactly ±10.75 pixels for a 0.05s input at the existing walk speed. The legacy 2D walk clocks and gameplay movement were not changed.
- Native controller retains the previously displayed pose and blends ordinary clip/state/new-action changes over 0.06s. Quaternions use shortest-path slerp; root offset uses the same weight. Interrupting a blend starts from the pose actually displayed. Reaction, block, KO and held contact peaks bypass blending immediately. Blend time advances only in unpaused world time, freezes during global/local hitstop and contact hold, and clears on reset. Clip/frame diagnostics still identify the native target clip/frame; only pose rotations/root offset are blended.
- Generic native sparks, rings and floating text now anchor to the victim's currently sampled canvas shift plus the local chest point rotated by the displayed canvas tilt. Sampling current controller state rather than the previous `visual_shift` prevents deferred taikou cues from using the pre-contact position. The 2D effect anchor stays unchanged. No logical fighter position, collision or damage was changed.
- Default taikou approach distance was left unchanged pending the root's actual default-bot rendered capture evidence. Layer, motion JSON and GLBs were not edited in this follow-up.

New `tests/battle_transition_check.gd` exercises real NativeMotion and Fighter/Arena behavior. Its first run failed 19 cases (`integration-review-fixes-red.log`, 24/43 passed), covering the four role/facing retreat cases, idle/walk-to-action blend starts, 0.03s halfway blends and incorrect deferred spark anchoring. After the fixes it passed 43/43 with native 3D enabled (`integration-review-fixes-green.log`). Tests also verify native frame diagnostics, 0.06s completion, pause/global/local hold freeze, reset, immediate reaction and exact contact bypass.

After the final production changes, all previously listed suites were rerun and passed with their previous check counts. Their new logs are `integration-reviewed-<test>.log`; native motion now reports 1502 samples and max support error 0.012953m against the root's finalized grounded assets. Both native startup modes again passed the 14/14 live integration check in `integration-reviewed-live-taikou.log` and `integration-reviewed-live-realtime.log`. The known host root-certificate-store diagnostic remains; no GDScript or renderer setup errors were present.

## Normal-spawn spatial contact follow-up

The root's actual default-bot screenshot at logical spawns 430/850 showed contact being held with the foe cross fist hundreds of pixels from the victim. The earlier QA harness's close initial positions did not prove normal-spawn contact. New tests now explicitly retain normal spawns and initial idle shifts.

Arena calibrates each native taikou exchange from the root-owned pure `Layer.anchor_offset()` API, which predicts the actual imported rig/camera/canvas offsets without writing live bones. It samples the attack's exact contact pose and the target's impact reaction0 (KO0 for a fatal target), including the existing 40px recoil and 9-degree tilt. Jab uses lead hand, cross uses rear hand, wave uses the palms midpoint. The target contact point lies on the head/chest front-surface segment at the height nearest that hand. The required extra X lunge is added to the existing 110px pulse; only canvas shift changes.

The extra lunge uses smooth easing from zero to exact contact at 0.48s, freezes during the existing hold, and eases back to the logical base by 1.12s. A restrained rush overlay drives only thigh/shin rotations during a large approach; it does not change authored upper-body rotations or root offsets and is zero exactly at contact. Frame diagnostics and exact contact/KO sampling remain intact.

Generic deferred spark/ring/text and the deterministic rhythm spark now share the calibrated body contact point. Realtime native generic effects anchor to the actual projected chest; 2D effects keep their prior anchor. The previous approximate chest-offset assertion in the transition test was replaced with an independently projected real hand/head/chest expectation, consistent with the new anchor requirement; no hold, clock or gameplay assertions were removed.

Shadow inspection confirmed that the override's `_draw_shadow(visual_shift)` already sets its own draw transform before the early return. The actual defect was missing redraw invalidation when native presentation moves under frozen gameplay. Arena now queues Fighter redraw when native canvas shift/tilt changes. A new draw-signal regression stops all Fighter ticks and verifies a presentation-only shift causes a fresh shadow draw while logical X stays 430.

Observed red/green evidence:

| Case | Red | Green |
|---|---|---|
| Normal-spawn projected contact and generic FX | 46/58; hand/body gaps player jab326.395, cross348.520, wave345.280; foe jab285.853, cross288.910, wave277.277px | 58/58; all six horizontal gaps 0.000px |
| Shared deterministic rhythm spark | 58/64; missing shared anchor | 70/70 including all six exact shared anchors |
| Calibrated controller shift | 39/40; ignored extra offset | Passed, native jab still frame6 at held contact |
| Approach leg motion | 42/44; no lower-leg dash | 44/44; legs animated, hands/root unchanged |
| Shadow redraw without Fighter tick | draw count1->1, failure | draw count1->2, pass; shift23.57143, logical pos430/520 |

Logs: `integration-contact-spacing-red.log`, `integration-contact-spacing-green.log`, `integration-contact-rhythm-red.log`, `integration-contact-rhythm-green.log`, `integration-approach-controller-red/green.log`, `integration-dash-legs-red/green.log`, `integration-shadow-red/green.log`.

After the final spatial production changes, all legacy/current pure suites were rerun successfully in `integration-spatial-final-<test>.log`: controller44/44; rules/flow/rage/rhythm/P0/engine/skin/motion/portrait/redraw counts unchanged; native motion1502 samples; root native rig124 checks. Native live integration remains14/14 in both startup modes (`integration-spatial-final-live-taikou.log`, `integration-spatial-final-live-realtime.log`). The updated transition suite is43/43 (`integration-spacing-transition-green.log`), spatial suite70/70 (`integration-contact-rhythm-green.log`), and shadow test passes (`integration-spatial-final-shadow.log`).

The new zero gaps certify predicted rig/canvas socket alignment; they do not substitute for inspecting glove volume, mesh overlap, transient dash sole placement or final Composition in actual Compatibility-renderer images. The root is recapturing the unmodified-spawn bot match for that final visual check. No gameplay position, reach, collision, damage, rank, meter, phase duration, data JSON, layer implementation or model file was changed by integration in this follow-up.
