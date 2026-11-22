"""H 路线 P0：证明 apose_points 口径，并为对手怪生成自己的 motion_input。

F 的 RigDriver 用 motion["apose_points"] 当**旋转中心 hv**（米，Blender
(x, z)），而 global_rest 从各自 GLB 的 Skeleton3D 读回。两个模型的 13 骨
rest 不同（对手怪更矮更宽），所以旋转中心必须各用各的骨架，否则会绕
错误的位置转。

先按固定规则从玩家 rig 重算 apose_points，与 F 的 motion_input.json
逐项对账（这是对规则的证明）；同一函数再从对手怪 rig 生成 foe 版。
除 apose_points 外其余键（stance / cards / mapping / bones / chain /
px_to_m / source / joint_names）逐项保持不变。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
PROBE = HERE / "data" / "blend_probe_h.json"
SRC = BAKE / "route-f-godot-driver" / "data" / "motion_input.json"
OUT_FOE = HERE / "data" / "motion_input_foe.json"
OUT_REPORT = HERE / "data" / "apose_crosscheck_h.json"


def xz(v: list[float]) -> list[float]:
    return [round(float(v[0]), 6), round(float(v[2]), 6)]


def apose_from_rig(rig: dict) -> dict:
    b = {x["name"]: x for x in rig["bones"]}
    need = ["hips", "spine", "chest", "neck", "head",
            "forearm_f", "forearm_b", "shin_f", "shin_b",
            "thigh_f", "thigh_b"]
    assert all(n in b for n in need), sorted(b)
    out = {
        "A": xz(b["hips"]["head"]),
        "B": xz(b["spine"]["head"]),
        "C": xz(b["chest"]["head"]),
        "D": xz(b["neck"]["head"]),
        "E": xz(b["head"]["head"]),
        "F": xz(b["head"]["tail"]),
        "f_elbow": xz(b["forearm_f"]["head"]),
        "f_hand": xz(b["forearm_f"]["tail"]),
        "b_elbow": xz(b["forearm_b"]["head"]),
        "b_hand": xz(b["forearm_b"]["tail"]),
        "f_knee": xz(b["shin_f"]["head"]),
        "f_foot": xz(b["shin_f"]["tail"]),
        "b_knee": xz(b["shin_b"]["head"]),
        "b_foot": xz(b["shin_b"]["tail"]),
        "tf_head": xz(b["thigh_f"]["head"]),
        "tb_head": xz(b["thigh_b"]["head"]),
    }
    # 三个语义别名（make_points 用的是 2D frame joints，这里只为结构一致）
    out["hip"] = out["A"]
    out["shoulder"] = out["D"]
    out["head"] = out["F"]
    return out


def main() -> int:
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    src = json.loads(SRC.read_text(encoding="utf-8"))
    player_rig = probe["blends"]["player"]["rigs"][0]
    foe_rig = probe["blends"]["foe"]["rigs"][0]

    rebuilt = apose_from_rig(player_rig)
    expect = {k: [round(float(x), 6) for x in v]
              for k, v in src["apose_points"].items()}
    rows = []
    for k in sorted(expect):
        got = rebuilt.get(k)
        diff = (max(abs(a - b) for a, b in zip(got, expect[k]))
                if got else None)
        rows.append({"key": k, "rebuilt": got, "expected": expect[k],
                     "max_abs_diff": diff})
    worst = max((9.9 if r["max_abs_diff"] is None
                 else r["max_abs_diff"]) for r in rows)
    same_keys = set(rebuilt) == set(expect)
    checks = {
        "apose_key_set_identical": same_keys,
        "player_rebuild_matches_F": worst <= 1e-4,
        "foe_rest_differs_from_player": (
            foe_rig["bones"] != player_rig["bones"]),
        "foe_apose_not_equal_player": None,
    }
    foe_apose = apose_from_rig(foe_rig)
    checks["foe_apose_not_equal_player"] = foe_apose != rebuilt

    # 只换 apose_points 一个键；其余（含 source/joint_names/stance/cards/
    # mapping/bones/chain/px_to_m）逐项保持原值，真相来源不被改写。
    foe = dict(src)
    foe["apose_points"] = foe_apose
    report = {
        "rule": "apose[u] = Blender bone.head_local/tail_local (x, z)",
        "player_worst_abs_diff": worst,
        "rows": rows,
        "foe_apose": foe_apose,
        "keys_other_than_apose_identical": all(
            foe[k] == src[k] for k in src if k != "apose_points"),
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "ok": (all(checks.values())
               and all(foe[k] == src[k] for k in src if k != "apose_points")),
    }
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")
    for r in rows:
        print(f"{r['key']:<10} rebuilt={str(r['rebuilt']):<24} "
              f"expected={str(r['expected']):<24} diff={r['max_abs_diff']}")
    print("WORST", worst, "SAME_KEYS", same_keys)
    for k, v in checks.items():
        print("CHECK", k, v)
    if report["ok"]:
        OUT_FOE.write_text(json.dumps(foe, ensure_ascii=False,
                                      separators=(",", ":"))
                           + "\n", encoding="utf-8")
        print("WROTE", OUT_FOE.name, OUT_FOE.stat().st_size, "B")
        print("APOSE_FOE_MOTION_OK")
        return 0
    print("APOSE_FOE_MOTION_FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
