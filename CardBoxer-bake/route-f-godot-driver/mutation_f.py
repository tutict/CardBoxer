"""F 路线变异验证：改坏东西，确认判据真的报红。

两层，各自独立：
  · 静态层  —— 改源码形状 / 数据 JSON / 清单，跑 verify_f.py 应红。
  · 运行时层 —— 只改 GDScript 的**公式数值**（不改关键字形状），
    静态形状守卫不该红；但重跑带窗口 Godot 驱动探针 +
    crosscheck_godot_pose.py 必须红。这证明「Blender 基准真的是独立锚点」，
    不是「守卫只会对着字符串叫」。

纪律（本机踩过的坑，全部写进实现）：
  · needle / mutant 只能是 ASCII bytes，含中文会 SyntaxError。
  · 锚点失配 = DID NOT RUN 并计入未证明，不崩、不跳过 clean re-run。
  · 还原必须逐字节 + sha256 证明（read_text/write_text 会转换换行）。
  · 运行时重跑会覆盖 data/ 下两个产物 JSON，必须一并备份还原，
    否则清单 sha 判据会连锁变红，掩盖真实原因。
  · 守卫跑禁字节码（PYTHONDONTWRITEBYTECODE=1）。
  · 负对照必须选清单外且 verify 不读的文件（logs/），否则会被 F03 抓到，
    负对照就假了。

用法：python mutation_f.py [--selftest]
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
OUT_MAIN = LOGS / "mutation_f_result.json"
OUT_SELFTEST = LOGS / "mutation_f_selftest_result.json"
PY = sys.executable

DRIVE_JSON = HERE / "data/godot_drive_probe.json"
POSE_JSON = HERE / "data/godot_pose_crosscheck.json"

# id, 相对路径, needle(bytes ASCII), mutant(bytes ASCII), 说明
STATIC_CASES = [
    ("M01", "probe_project_f/scenes/rig_driver.gd",
     b"var theta := -deg_to_rad(", b"var theta := deg_to_rad(",
     "A05 旋转轴符号"),
    ("M02", "probe_project_f/scenes/rig_driver.gd",
     b"gr_parent.affine_inverse() * local * gr",
     b"gr.affine_inverse() * local * gr",
     "A04 pose 基底（真实修过的 bug）"),
    ("M03", "probe_project_f/scenes/rig_driver.gd",
     b"pose_mat = c * gr", b"pose_mat = gr",
     "A04 根骨 root 平移"),
    # 不改成函数名：那会让调用处解析失败，证明的是「文件坏了」，
    # 不是「守卫有牙」。这里只改一个常量断言，语法仍成立。
    ("M04", "probe_project_f/scenes/rig_driver.gd",
     b"bone_names.size() == 13 and chain.size() == 13",
     b"bone_names.size() == 12 and chain.size() == 12",
     "A06 13 骨形状"),
    ("M05", "probe_project_f/scenes/player_driven.gd",
     b'MOTION_PATH := "res://data/motion_input.json"',
     b'MOTION_PATH := "res://data/motion_input_BROKEN.json"',
     "A08 场景只读运动输入"),
    ("M06", "probe_project_f/scenes/player_driven.gd",
     b'preload("res://scenes/rig_driver.gd")',
     b'preload("res://scenes/rig_driver_BROKEN.gd")',
     "A07 场景 preload 驱动层"),
    ("M07", "data/motion_input.json",
     b'"torso_gain":0.35', b'"torso_gain":0.95',
     "A14 运动输入独立复算"),
    ("M08", "data/rigged_gltf_inspection.json",
     b'"highpoly_has_skin": true', b'"highpoly_has_skin": false',
     "B03 高模带 skin"),
    ("M09", "data/godot_rig_probe.json",
     b'"bone_count": 14', b'"bone_count": 13',
     "B09 Godot 14 骨"),
    ("M10", "data/godot_drive_probe.json",
     b'"frame_count": 73', b'"frame_count": 72',
     "C04 73 帧"),
    ("M11", "data/godot_pose_crosscheck.json",
     b'"ok": true', b'"ok": false',
     "C06 三重对账全绿"),
    ("M12", "data/godot_render_f.json",
     b'"stage_ready": true', b'"stage_ready": false',
     "D03 主场景 ready"),
    ("M13", "probe_project_f/probes/render_driven.gd",
     b'SCENE_PATH := "res://scenes/player_driven.tscn"',
     b'SCENE_PATH := "res://scenes/player_driven_BROKEN.tscn"',
     "A12 截帧走同一条场景链"),
    ("M14", "probe_project_f/probes/probe_drive.gd",
     b'["stance", 0]', b'["stance", 1]',
     "A11 探针帧表"),
    ("M15", "data/board_stats_f.json",
     b'"count": 4', b'"count": 3',
     "F03 清单 sha 自洽（改了交付文件就应报红）"),
]

# 运行时层：改公式数值，不改任何被 verify 检查的形状关键字。
RUNTIME_CASES = [
    # 注意：motion.get("px_to_m", 0.01) 只是 fallback，JSON 里有这个键，
    # 改它不会改变任何运行时数值；必须改真正执行的 dx/dz 公式。
    ("R01", "probe_project_f/scenes/rig_driver.gd",
     b'var dx: float = (frame_j["hip"].x - stance["hip"].x) * px_to_m',
     b'var dx: float = (frame_j["hip"].x - stance["hip"].x) * px_to_m * 2.0',
     "root 位移比例翻倍 -> root_matches_blender 应红"),
    ("R02", "probe_project_f/scenes/rig_driver.gd",
     b'var tf := minf(1.0, mf / float(mapping["reach_norm_px"]))',
     b'var tf := minf(1.0, mf / float(mapping["wave_min_norm_px"]))',
     "手臂归一常数被换 -> delta_matches_blender 应红"),
    ("R03", "probe_project_f/scenes/rig_driver.gd",
     b'var used := clampf(torso * float(mapping["torso_gain"]), -cap, cap)',
     b'var used := clampf(torso * float(mapping["torso_gain"]) * 2.0, -cap, cap)',
     "躯干增益翻倍 -> delta_matches_blender 应红"),
    ("R04", "probe_project_f/scenes/rig_driver.gd",
     b'var theta := -deg_to_rad(float(delta_deg[n]))',
     b'var theta := -deg_to_rad(float(delta_deg[n])) * 0.5',
     "旋转角折半 -> engine_vs_blender 应红"),
]

# 负对照：logs/ 被清单排除，verify 也不读它；改了不该报红。
NEGATIVE = ("N01", "logs/run_probe_rig.out",
            b"IMPORT rc=0", b"IMPORT rc=9",
            "负对照：清单外且 verify 不读")

ALL_CASES = STATIC_CASES + RUNTIME_CASES + [NEGATIVE]


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def env_no_bytecode() -> dict:
    e = os.environ.copy()
    e["PYTHONDONTWRITEBYTECODE"] = "1"
    return e


def run(cmd: list[str], timeout: int = 240) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=str(HERE), capture_output=True,
                       text=True, env=env_no_bytecode(), timeout=timeout)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run_verify() -> tuple[int, str]:
    return run([PY, str(HERE / "verify_f.py")])


def run_runtime_chain() -> tuple[bool, str]:
    """重跑带窗口驱动探针 + 三重对账；返回 (是否报红, 摘要)。"""
    r1, o1 = run([PY, str(HERE / "run_probe_drive.py")])
    r2, o2 = run([PY, str(HERE / "crosscheck_godot_pose.py")])
    red = (r1 != 0 or r2 != 0
           or "GODOT_POSE_CROSSCHECK_FAILED" in o2
           or "MOTION_INPUT_FAILED" in o2)
    summary = []
    for line in (o1 + o2).splitlines():
        if ("FAILED" in line or "WORST" in line
                or line.strip().startswith("FAIL")):
            summary.append(line.strip())
    return red, " | ".join(summary[:6])


def main() -> int:
    selftest = "--selftest" in sys.argv
    LOGS.mkdir(parents=True, exist_ok=True)
    # 运行时重跑会覆盖这两个产物，先备份原始字节。
    saved_drive = DRIVE_JSON.read_bytes()
    saved_pose = POSE_JSON.read_bytes()
    saved_sha = {"drive": sha256(saved_drive), "pose": sha256(saved_pose)}

    results = []
    for cid, rel, needle, mutant, desc in ALL_CASES:
        if selftest and cid == "M01":
            needle = b"__THIS_ANCHOR_DOES_NOT_EXIST__"
        p = HERE / rel
        original = p.read_bytes()
        digest = sha256(original)
        count = original.count(needle)
        if count != 1:
            results.append({"id": cid, "file": rel, "status": "DID NOT RUN",
                            "reason": f"anchor count={count}", "desc": desc})
            print(f"{cid} DID NOT RUN  anchor count={count}  {rel}")
            continue
        p.write_bytes(original.replace(needle, mutant, 1))
        is_runtime = cid.startswith("R")
        is_negative = cid.startswith("N")
        try:
            rc, out = run_verify()
            static_red = rc != 0 and "F_VERIFY_FAILED" in out
            failed = [l.strip().split()[-1] for l in out.splitlines()
                      if l.strip().startswith("FAIL")]
            row = {"id": cid, "file": rel, "static_red": static_red,
                   "static_returncode": rc,
                   "failed_checks": failed[:8], "desc": desc}
            if is_runtime:
                runtime_red, summary = run_runtime_chain()
                row["runtime_red"] = runtime_red
                row["runtime_summary"] = summary
                row["status"] = "CAUGHT" if runtime_red else "MISSED"
            elif is_negative:
                row["status"] = "MISSED" if not static_red else "CAUGHT"
            else:
                row["status"] = "CAUGHT" if static_red else "MISSED"
            results.append(row)
            print(f"{cid} {row['status']:<11} static={'RED' if static_red else 'GREEN'} "
                  + (f"runtime={'RED' if row.get('runtime_red') else 'GREEN'} "
                     if is_runtime else "")
                  + f" failed={failed[:3]}  {desc}")
        finally:
            p.write_bytes(original)
            DRIVE_JSON.write_bytes(saved_drive)
            POSE_JSON.write_bytes(saved_pose)
        restored = (sha256(p.read_bytes()) == digest
                    and sha256(DRIVE_JSON.read_bytes()) == saved_sha["drive"]
                    and sha256(POSE_JSON.read_bytes()) == saved_sha["pose"])
        results[-1]["restored"] = restored
        if not restored:
            print(f"{cid} RESTORE FAILED  {rel}")

    # clean re-run：源码与产物都已还原，静态验收必须全绿；
    # 运行时链也要重跑一次，证明还原后引擎输出仍与 Blender 等价。
    clean_rc, clean_out = run_verify()
    clean_green = (clean_rc == 0 and "F_VERIFIED" in clean_out
                   and "F_VERIFY_FAILED" not in clean_out)
    runtime_clean_red, _ = run_runtime_chain()
    DRIVE_JSON.write_bytes(saved_drive)
    POSE_JSON.write_bytes(saved_pose)
    runtime_clean_green = not runtime_clean_red

    caught = sum(1 for r in results if r["status"] == "CAUGHT")
    did_not_run = sum(1 for r in results if r["status"] == "DID NOT RUN")
    missed = sum(1 for r in results if r["status"] == "MISSED")
    restored = sum(1 for r in results if r.get("restored", True))
    n_static = len(STATIC_CASES)
    n_runtime = len(RUNTIME_CASES)
    expect_caught = n_static + n_runtime - (1 if selftest else 0)
    negative = next((r for r in results if r["id"] == "N01"), None)
    negative_ok = negative is not None and negative["status"] == "MISSED"
    # 任何 DID NOT RUN 都计入未证明，整体验收必须失败；
    # selftest 正是靠这条拿到「not ok」，证明失配分支有牙。
    ok = (caught == expect_caught and did_not_run == 0
          and missed == 1  # 只有负对照 N01 允许 MISSED
          and restored == len(results)
          and clean_green and runtime_clean_green and negative_ok)
    payload = {
        "selftest": selftest,
        "cases": len(ALL_CASES),
        "static_cases": n_static, "runtime_cases": n_runtime,
        "caught": caught, "did_not_run": did_not_run, "missed": missed,
        "restored": restored, "expect_caught": expect_caught,
        "negative_control_ok": negative_ok,
        "clean_rerun_green": clean_green,
        "runtime_clean_green": runtime_clean_green,
        "clean_returncode": clean_rc,
        "ok": ok, "results": results,
    }
    (OUT_SELFTEST if selftest else OUT_MAIN).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"SUMMARY caught={caught}/{expect_caught} "
          f"did_not_run={did_not_run} missed={missed} "
          f"restored={restored}/{len(results)} "
          f"clean={'GREEN' if clean_green else 'RED'} "
          f"runtime_clean={'GREEN' if runtime_clean_green else 'RED'} "
          f"negative={'OK' if negative_ok else 'BAD'}")
    if selftest:
        good = did_not_run == 1 and not ok
        print("SELFTEST_ASSERTION_OK" if good else "SELFTEST_ASSERTION_FAILED")
        return 0 if good else 1
    print("MUTATION_F_OK" if ok else "MUTATION_F_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
