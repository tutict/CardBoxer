# Task: battle presentation and gameplay integration

Read ../contracts.md first; interface names and NativePose structure are binding.
Own project/scripts/arena.gd, fighter.gd, battle_presentation.gd,
project/tests/battle_presentation_check.gd and integration-specific tests only.
Root owns rig_driver/fighter_3d_layer; author owns native_motion/data; QA owns captures.
Implement on this task's isolated project, never the actual sibling game.

Write/run failing regression tests first (guard missing methods/ResourceLoader.exists
instead of parse errors), then implement. User approved native 3D arcade poses,
both roles/all 15 existing motions, taikou+realtime, preserve gameplay rules.

Use Fighter.presentation_snapshot with action_seq, phase/progress/time, own hitstop,
state/reaction time, facing, walk_phase (actual distance), walk_blend, movement,
guard/dodge/super/hp. Increase action_seq on play_card/perform_visual, preserve
terminal action IDs before freeze. Snapshot is read-only, no gameplay mutations.

BattlePresentation setup(NativeMotion), reset(round_id), begin_exchange, record_impact,
advance(dt,context), sample(role,snapshot,context) -> visual {pose,facing,canvas_shift,
canvas_tilt,clip_id,frame,frozen}. Priority after contact: terminal KO > hit/block >
contact latch > action > walk/idle. Use native library; no direct raw 2D retarget.
Root's layer.apply_visual consumes pose/facing/canvas_tilt; arena sets layer position.
If native library fails, report clear error and leave existing 2D drawing active.

Realtime ACTION uses exact existing Defs windup/active/recover clocks and last-active
hit tick. Read actual hitstop for contact latch, not a new global pause. Reaction
starts on its native impact pose. wave release occurs on active last tick, later
projectile collision is independent: must not force attacker's current new action
back to wave. Idle/walk based on actual distance; guarding after action may persist.
Facing obeys existing ACTION/HITSTUN locks; root rotates models, no bone mirror.

Taikou: reveal 1.5s, resolve 1.9s (logical time), attack 1.12s, contact 0.48s.
Piecewise source frame sampling 0..contact_frame before contact, contact..last frame
after. Crossing contact clamps to exact pose, emits cue once, freezes with existing
0.24s global hitstop before consuming remaining visual time. Do not freeze past peak.
HP/rage/result still settle in _resolve_taikou where they do now. Capture immediate
hit_confirmed FX into deferred presentation cues for 3D taikou: trigger hit reaction,
spark/text/knockback/tilt/HIT once on contact; remove premature duplicate 0.07 hold in
this path. Block/dodge behavior unchanged for realtime. No duplicate apply_hit/signals.
Reaction durations from current Fighter: block .16, normal .26, launch .42,
stun_long .5, super .75. Draw: both light reactions start immediately, no winner attack.

Visual randomness: _push_spark/_push_float_text/_shake_offset use a dedicated RNG,
not the gameplay global RNG. New same-version 2D/3D should not change card randomness;
old mixed-RNG seed replay is intentionally not a compatibility target.

Terminal: capture exchange before immediate over/freeze. Independent presentation
must finish fatal attack -> contact -> .45s ko -> hold even over. Gameplay still
ends immediately; no projectile/new hit settling after over. Winner returns guard.
Pause freezes visual clock, slowmo uses world dt, hitstop advances hold only.
New round / R clears queues, terminal, blend, shifts, old round/action event IDs.

Add CARD_BOXER_BATTLE_MODE=taikou|realtime at startup, taikou default. Existing 3D
toggle retained. Keep 2D motion tables and collision/movement/frame/rules values.
Use pure tests for .479/.480/.481, 30/60/120fps crossing, repeated cues, draw, late
wave collision after new action, terminal KO, reset, pause and slow motion; live
integration tests fixed deck/input. Don't add production test-only hooks.

Notify root when controller interfaces are ready. Put full test report/concerns in
reports/integration-report.md. No git commits, no external installs.
