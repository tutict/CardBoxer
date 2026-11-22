# Shared implementation contracts

Engine Godot 4.5, GDScript. Preload scripts explicitly (new class_name cache is stale).
Work only in project/ and owned tooling files under this task folder.

## NativeMotion — scripts/native_motion.gd + data/combat_motion_3d.json

extends RefCounted. Public:
- load_data(path: String = "res://data/combat_motion_3d.json") -> bool
- sample(role: String, clip_id: String, frame_float: float) -> Dictionary
- phase_frame(role: String, clip_id: String, phase: String, progress: float) -> float
- contact_frame(role: String, clip_id: String) -> float
- clip_frames(role: String, clip_id: String) -> int
- available() -> bool

Roles: player, foe. Clips: stance, idle, walk, ko; all 12 Defs.CARDS; hit_light,
hit_heavy, block. Card split and frames copied from Defs/current motion inputs.
contact_frame is windup+active-1 for melee/release; nonattack clips use -1.
Use smooth continuous short-path quaternion slerp. At each phase's progress=1,
return its final authored frame (no wrap into next phase). Reaction first key is
the impact, last key returns to guard. Card endpoints return to guard.

JSON version=1, coordinate_system="godot_y_up_z_forward", bones=13 names;
roles.<role>.clips.<clip> = {frames, split, contact_frame, keys:[{frame,
rotations:{bone:[x,y,z,w]}, root_offset:[x,y,z]}]}. stance frames=1,
idle/walk may loop, ko frames=28 (27 intervals at 60fps ~=0.45s), KO ends down.
All quaternions are local rest-relative, normalized; Godot +Y up, model +Z forward.
NativePose output: {clip_id:String, frame:float, rotations:Dictionary,
root_offset:Array[3]}. Use both models' own rest to author/correct their poses.

## Driver/layer (root-owned)

RigDriver.apply_pose(pose: Dictionary) -> Dictionary consumes NativePose.
For each driven bone: q_local = q_rest * q_delta, rest local position and scale;
root_offset added once to hips in skeleton space. neutral_bone unchanged.
Retain setup + apply_frame for legacy diagnostics.
Fighter3DLayer.apply_visual(visual: Dictionary) -> void consumes
{pose:NativePose, facing:int, canvas_tilt:float}. layer position is set by arena
to fighter.position + visual.canvas_shift. Native mode skips _apply_stance_bias.
set_facing(facing:int) rotates imported model around Y when its face changes;
base player faces +1, base foe faces -1 with their existing cameras.

## Fighter/presentation/arena (integration-owned)

Fighter.presentation_snapshot() -> Dictionary is read-only and includes state,
card_id, action_seq, phase, phase_progress, phase_time, state_time,
stun_duration, local_hitstop, facing, walk_phase, walk_blend, moving,
guarding, dodging, is_super, hp. Increase action_seq for new action/visual.

BattlePresentation (scripts/battle_presentation.gd) owns native sampling,
contact latches and terminal visual clocks. setup(library), reset(round_id),
begin_exchange(exchange:Dictionary), record_impact(impact:Dictionary),
advance(dt:float, context:Dictionary), sample(role:String,snapshot:Dictionary,
context:Dictionary)->Dictionary. Exact internals left to owning implementer.
Result visual: {pose:NativePose, facing:int, canvas_shift:Vector2,
canvas_tilt:float, clip_id:String, frame:float, frozen:bool}.
Context supplies mode, round_phase, global_hitstop, pause, terminal state.

Native controller may expose additional read-only diagnostics for tests, but keep
test setup out of production. Events carry round_id + action_seq + actor/target,
blocked/dodged/terminal and source_kind (melee, projectile, taikou/release).
Do not replay apply_hit, card signals, meter, or RNG from presentation cues.

## Test/tool ownership

Root: tests/native_rig_check.gd; rig_driver.gd; fighter_3d_layer.gd; rendering QA.
Motion author: native_motion.gd, combat_motion_3d.json, tests/native_motion_check.gd,
              author_native_motion.* / authoring probes if needed.
Integration: arena.gd, fighter.gd, battle_presentation.gd,
             tests/battle_presentation_check.gd and integration-specific probes.
QA: tests/native_motion_capture.gd, tests/native_live_check.gd (after interfaces
settle), render/capture Python/PowerShell tools and reports under task folder.
No shared-file edits without coordinating. Install is root-only.

## Runtime

Godot: C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe
Bundled CPython: C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1118-904-0_26.1118.904.0_x64__3k8sg7r9htsxt/dependencies/python/python.exe
For render captures, a real Compatibility renderer is required; dummy headless
renderer cannot prove model image quality. Launch helpers with hidden windows.
No destructive git commands, no git commits (source project has no git history).
