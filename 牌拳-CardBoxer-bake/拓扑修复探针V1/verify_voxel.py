"""承重判据：证明「不需要 ZBrush」这个结论有可复算数字，且没藏负结果。

不评好看、不评排版、不声称变形可用。判据只钉：
  碎壳 -> 体素重建 -> 自动权重覆盖率；权重回传后原件资产是否保住；
  变形 A/B 数字；负结果有没有被写成通过；归档与游戏源码有没有被动过。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
BLEND = BAKE / "对手怪Blender建模V1" / "对手怪V1.blend"
BASELINE_SHA = "76004e212759c76f8f84a5d8fbab58680eedc4ebcd11d663e783f8c234e13165"

voxel = json.loads((HERE / "voxel_probe.json").read_text(encoding="utf-8"))
transfer = json.loads((HERE / "transfer_probe.json").read_text(encoding="utf-8"))
note = (HERE / "拓扑修复探针-结论.txt").read_text(encoding="utf-8")
cases = {c["case"]: c for c in voxel["cases"]}

checks = []


def check(name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})


def independent_shells(faces):
    """进程外独立 union-find，不复用 Blender 脚本里的实现。"""
    n = max(max(f) for f in faces) + 1
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for f in faces:
        for v in f[1:]:
            a, b = find(f[0]), find(v)
            if a != b:
                parent[b] = a
    used = {v for f in faces for v in f}
    return len({find(v) for v in used})


# 1. 归档没被回写
sha = hashlib.sha256(BLEND.read_bytes()).hexdigest()
check("source_blend_unchanged", sha == BASELINE_SHA, f"sha={sha[:12]}")

# 2. 基线确实是 Bone Heat 0 覆盖（同口径实测，不引用旧日志）
raw = cases["raw_no_remesh"]
check("baseline_bone_heat_really_zero",
      raw["auto_weight"]["coverage"] == 0.0 and raw["after_remesh"]["shells"] == 2809,
      f"shells={raw['after_remesh']['shells']} coverage={raw['auto_weight']['coverage']}")

# 3/4. 0.020 档：壳塌缩 + 自动权重拉起
c20 = cases["v0p02"]
check("voxel_020_collapses_shells", c20["after_remesh"]["shells"] <= 3,
      f"2809 -> {c20['after_remesh']['shells']}")
check("voxel_020_autoweight_recovered", c20["auto_weight"]["coverage"] >= 0.99,
      f"{c20['auto_weight']['covered']}/{c20['auto_weight']['total']} = "
      f"{c20['auto_weight']['coverage']}")

# 5/6. 0.035 档：更粗体素，全覆盖
c35 = cases["v0p035"]
check("voxel_035_collapses_shells", c35["after_remesh"]["shells"] <= 2,
      f"2809 -> {c35['after_remesh']['shells']}")
check("voxel_035_autoweight_full", c35["auto_weight"]["coverage"] == 1.0,
      f"{c35['auto_weight']['covered']}/{c35['auto_weight']['total']}")

# 7. 独立复核壳数（不经 Blender）
cross = []
for tag, case in (("v0p02", c20), ("v0p035", c35)):
    fp = HERE / f"faces_{tag}.json"
    faces = json.loads(fp.read_text(encoding="ascii"))
    n = independent_shells(faces)
    cross.append((tag, n, case["after_decimate"]["shells"]))
ok_cross = bool(cross) and all(a == b for _, a, b in cross)
check("independent_shell_crosscheck", ok_cross,
      "; ".join(f"{t}: indep={a} blender={b}" for t, a, b in cross))

# 8. 权重回传后原高模的 UV / 材质 / PBR 贴图逐项保住
tr = transfer["transfer"]
kept = tr["assets_kept"]
check("transfer_keeps_original_assets",
      tr["coverage"] >= 0.99 and kept["uv_same_as_source"]
      and kept["textures_same_as_source"] and len(kept["textures"]) == 3,
      f"coverage={tr['coverage']} uv={kept['uv_layers']} "
      f"textures={len(kept['textures'])} same={kept['textures_same_as_source']}")

# 9/10. 变形数字：最大位移下降、影响范围扩大（权重更连续）
a, b = transfer["deform_a_rigid"], transfer["deform_b_transfer"]
check("transfer_reduces_max_displacement",
      b["max_displacement_m"] < a["max_displacement_m"],
      f"A={a['max_displacement_m']} m -> B={b['max_displacement_m']} m")
check("transfer_spreads_influence",
      b["moved_vertices_gt_0_1mm"] > a["moved_vertices_gt_0_1mm"],
      f"A={a['moved_vertices_gt_0_1mm']} -> B={b['moved_vertices_gt_0_1mm']}")

# 11. 点名本探针应产出的图，集合相等（多一张少一张都红），不写死数字
EXPECTED_PNGS = {
    "proxy-front.png",
    "transfer-rest-front.png",
    "transfer-compare-rigid.png",
    "transfer-compare-transfer.png",
}
pngs = sorted(HERE.glob("*.png"))
img_ok = {p.name for p in pngs} == EXPECTED_PNGS
img_detail = [f"set_equal={img_ok}"]
for p in pngs:
    im = Image.open(p).convert("RGB")
    colors = len(im.resize((96, 96)).getcolors(96 * 96) or [])
    img_detail.append(f"{p.name}:{im.size[0]}x{im.size[1]}/c{colors}")
    if im.size != (768, 768) or colors < 20 or p.stat().st_size < 10000:
        img_ok = False
check("renders_nonblank_and_nonuniform", img_ok, " ".join(img_detail))

# 12. 负结果没被藏：钉具体负结果句，不用宽松的「不可见」子串
#     （结论文件第七节另有一处「右臂不可见」，宽松判据会被绕过）
REQUIRED_NEGATIVE = ["A/B 两版", "右臂都不可见", "不证明变形可用", "不需要 ZBrush"]
missing = [s for s in REQUIRED_NEGATIVE if s not in note]
caveat_ok = ("不声称可用" in transfer["caveat"] and not missing)
check("negative_result_not_hidden", caveat_ok,
      f"caveat={transfer['caveat'][:24]}... missing={missing}")

# 13. 探针产物隔离，没有引擎文件、没动游戏源码
engine_files = [p.name for p in HERE.rglob("*")
                if p.suffix in {".gd", ".tscn", ".import", ".godot"}]
check("probe_outputs_are_isolated", not engine_files, f"engine_files={engine_files}")

# 14. 零软件成本可复算：两次 Blender 总耗时
total_s = voxel["elapsed_seconds"] + transfer["elapsed_seconds"]
check("runtime_is_negligible", total_s < 30, f"total={total_s}s (two Blender runs)")

passed = sum(1 for c in checks if c["ok"])
for c in checks:
    print(f"{'PASS' if c['ok'] else 'FAIL'}  {c['name']}  {c['detail']}", flush=True)
print(f"\n{passed}/{len(checks)} PASS  "
      f"{'VOXEL_PROBE_VERIFIED' if passed == len(checks) else 'VOXEL_PROBE_FAILED'}",
      flush=True)

result = {"verdict": "VOXEL_PROBE_VERIFIED" if passed == len(checks) else "VOXEL_PROBE_FAILED",
          "passed": passed, "total": len(checks), "checks": checks}
(HERE / "verify_voxel_result.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
sys.exit(0 if passed == len(checks) else 1)
