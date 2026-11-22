"""只读：核对变异锚点在文件中的出现次数（必须唯一）。"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = [
    ("probe_project_f/scenes/rig_driver.gd", b"var theta := -deg_to_rad("),
    ("probe_project_f/scenes/rig_driver.gd",
     b"gr_parent.affine_inverse() * local * gr"),
    ("probe_project_f/scenes/rig_driver.gd", b"pose_mat = c * gr"),
    ("probe_project_f/scenes/rig_driver.gd", b"func retarget_delta("),
    ("probe_project_f/scenes/player_driven.gd",
     b'MOTION_PATH := "res://data/motion_input.json"'),
    ("probe_project_f/scenes/player_driven.gd",
     b'preload("res://scenes/rig_driver.gd")'),
    ("data/motion_input.json", b'"stance":{"hip":[0.0,-80.0]'),
    ("data/motion_input.json", b'"torso_gain":0.35'),
    ("data/godot_pose_crosscheck.json", b'"ok": true'),
    ("data/rigged_gltf_inspection.json", b'"highpoly_has_skin": true'),
    ("data/godot_render_f.json", b'"stage_ready": true'),
    ("data/godot_drive_probe.json", b'"frame_count": 73'),
    ("data/godot_rig_probe.json", b'"bone_count": 14'),
    ("probe_project_f/probes/render_driven.gd", b'"seq": 7,  "yaw"'),
    ("probe_project_f/probes/probe_drive.gd", b'"no RIG_JSON"'),
]

for rel, needle in CASES:
    p = HERE / rel
    n = p.read_bytes().count(needle) if p.is_file() else -1
    print(f"{n:>3}  {rel:<50} {needle[:48]!r}")
print("--- motion_input head ---")
print((HERE / "data/motion_input.json").read_text(encoding="utf-8")[:220])
