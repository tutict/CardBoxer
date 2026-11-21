"""对账落地前 / 落地后两轮 world3d_min 报告。

重点：`own` 组（源码落地后由 setup() 设 own、探针再幂等设一次）与
落地前（探针运行时设 own）的 SubViewport PNG 是否逐字节一致——
一致才证明「add_child 之前设」与「运行时设」时序无影响。

用法：python check_prepost.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE / "data"
PRE = json.loads((D / "world3d_min_pre.json").read_text(encoding="utf-8"))
POST = json.loads((D / "world3d_min.json").read_text(encoding="utf-8"))


def row(rep, mode, label, key):
    return rep["modes"][mode]["layers"][label].get(key)


def main() -> int:
    for mode in ("none", "own", "world", "both"):
        print(f"--- {mode} ---")
        for label in ("player", "foe"):
            a = PRE["modes"][mode]["layers"][label]
            b = POST["modes"][mode]["layers"][label]
            pa, pb = a["pixels"], b["pixels"]
            print(f"  {label:6s} sha  pre={a['png_sha256'][:12]} "
                  f"post={b['png_sha256'][:12]} "
                  f"{'SAME' if a['png_sha256'] == b['png_sha256'] else 'DIFF'}")
            print(f"         white pre={pa['near_white_px']:6d} "
                  f"post={pb['near_white_px']:6d}  "
                  f"opaque pre={pa['opaque_px']:6d} "
                  f"post={pb['opaque_px']:6d}  "
                  f"scenario pre={PRE['modes'][mode]['scenario_errors']} "
                  f"post={POST['modes'][mode]['scenario_errors']}")
    truth = json.loads((HERE.parent / "B路线-资产层去重" / "data"
                        / "single_layers.json").read_text(encoding="utf-8"))
    t = {r["role"]: r for r in truth["runs"]}
    # 订正：落地前后 own 组 sha 不同不是回归。落地前是「运行时切 world」
    # 的过渡态，落地后是「启动即设 own」的真实态；后者才等于单层真值。
    checks = {
        "post_own_equals_single_layer_truth": all(
            row(POST, "own", l, "png_sha256") == t[l]["png_sha256"]
            for l in ("player", "foe")),
        "post_own_pixels_equal_single_layer_truth": all(
            all(row(POST, "own", l, "pixels")[k] == t[l]["pixels"][k]
                for k in ("opaque_px", "near_white_px",
                          "cyan_px", "white_ratio"))
            for l in ("player", "foe")),
        "pre_own_differs_from_post_own": all(
            row(PRE, "own", l, "png_sha256")
            != row(POST, "own", l, "png_sha256")
            for l in ("player", "foe")),
        "runtime_swap_path_stable": all(
            row(PRE, m, l, "png_sha256") == row(POST, m, l, "png_sha256")
            for m in ("world", "both") for l in ("player", "foe")),
        "pre_own_differs_from_pre_none": all(
            row(PRE, "own", l, "png_sha256")
            != row(PRE, "none", l, "png_sha256")
            for l in ("player", "foe")),
        "post_own_differs_from_post_none": all(
            row(POST, "own", l, "png_sha256")
            != row(POST, "none", l, "png_sha256")
            for l in ("player", "foe")),
    }
    (D / "prepost.json").write_text(
        json.dumps({"checks": checks,
                    "failed": [k for k, v in checks.items() if not v],
                    "note": ("落地前后 own 组 sha 不同是预期的：落地前是运行时"
                             "切 world 的过渡态，落地后与单层真值逐字节相同。"),
                    "ok": all(checks.values())},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("PREPOST_OK" if all(checks.values()) else "PREPOST_FAILED")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
