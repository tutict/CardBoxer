"""建模阶段 14 条判据的变异验证：证明它们不是真空通过。

纪律：逐字节还原用 sha256 证明；锚点失配报 DID NOT RUN 并计入未证明；
每条点名一条应保持绿色的哨兵；跑完 clean re-run 必须 14/14。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERIFY = HERE / "verify_foe_build.py"
LOG = HERE / "verify_foe_build.log"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_verify() -> dict:
    p = subprocess.run([sys.executable, str(VERIFY)], capture_output=True, text=True)
    lines = [x for x in LOG.read_text(encoding="utf-8").splitlines()
             if x.startswith(("PASS", "FAIL"))]
    return {"exit": p.returncode,
            "red": [x.split()[1] for x in lines if x.startswith("FAIL")],
            "green": {x.split()[1] for x in lines if x.startswith("PASS")}}


CASES = [
    {
        "name": "M1", "desc": "把 100% 刚性权重覆盖改成 0.5（假装没覆盖全）",
        "target": "armature_13_bones_full_rigid_coverage",
        "sentinel": "blender_normalized_to_game_bridge",
        "path": HERE / "blender_build.json",
        "old": b'"coverage": 1.0', "new": b'"coverage": 0.5',
    },
    {
        "name": "M2", "desc": "把剪影未达标伪装成达标（负结果不能改成通过）",
        "target": "silhouette_measured_and_shortfall_not_hidden",
        "sentinel": "compare_board_valid",
        "path": HERE / "silhouette_stats.json",
        "old": b'"verdict": "SILHOUETTE_CONTRAST_SHORT"',
        "new": b'"verdict": "SILHOUETTE_CONTRAST_OK"',
    },
    {
        "name": "M3", "desc": "把骨架驱动最大位移改成 0（假装模型没动）",
        "target": "deform_probe_shows_motion_and_caveat",
        "sentinel": "auto_weights_honestly_zero",
        "path": HERE / "deform_probe.json",
        "old": b'"max_displacement_m": 0.47922',
        "new": b'"max_displacement_m": 0.0',
    },
    {
        "name": "M4", "desc": "给纯图生 3D 塞一个文字 prompt（伪装成文生 3D）",
        "target": "input_image_is_approved_design",
        "sentinel": "image_probe_no_resubmit_and_done",
        "path": HERE / "probe_report.json",
        "old": b'"prompt": null', "new": b'"prompt": "a cat"',
    },
]

results = []
for c in CASES:
    path: Path = c["path"]
    original = path.read_bytes()
    original_sha = sha(path)
    rec = {"name": c["name"], "caught": False, "target_red": False,
           "sentinel_green": False, "red": [], "did_not_run": False,
           "restore": False, "error": ""}
    results.append(rec)
    try:
        assert c["old"] in original, f"{c['name']} 锚点失配"
        assert original.count(c["old"]) == 1, f"{c['name']} 锚点不唯一"
        path.write_bytes(original.replace(c["old"], c["new"], 1))
        assert sha(path) != original_sha, f"{c['name']} 变异没改变字节"

        r = run_verify()
        rec["target_red"] = c["target"] in r["red"]
        rec["sentinel_green"] = c["sentinel"] in r["green"]
        rec["red"] = r["red"]
        rec["caught"] = bool(r["exit"] != 0 and rec["target_red"]
                             and rec["sentinel_green"])
    except (AssertionError, OSError, KeyError, json.JSONDecodeError) as e:
        rec["did_not_run"] = True
        rec["error"] = str(e)
    finally:
        path.write_bytes(original)
    rec["restore"] = sha(path) == original_sha
    status = ("DID NOT RUN" if rec["did_not_run"]
              else "CAUGHT" if rec["caught"] else "MISSED!")
    print(f"{c['name']} {status}  red={rec['target_red']} "
          f"sentinel_green={rec['sentinel_green']} restore={rec['restore']}  "
          f"{c['desc']}" + (f"  [{rec['error']}]" if rec["error"] else ""), flush=True)

final = run_verify()
clean = final["exit"] == 0 and not final["red"]
caught_n = sum(1 for r in results if r["caught"])
restored_n = sum(1 for r in results if r["restore"])
not_run_n = sum(1 for r in results if r["did_not_run"])
verdict = ("MUTATION_FOE_BUILD_OK"
           if caught_n == len(CASES) and restored_n == len(CASES)
           and not_run_n == 0 and clean
           else "MUTATION_FOE_BUILD_FAILED")
body = "\n".join(
    f"{r['name']} {'DID NOT RUN' if r['did_not_run'] else 'CAUGHT' if r['caught'] else 'MISSED!'}  "
    f"target_red={r['target_red']} sentinel_green={r['sentinel_green']} "
    f"restore={r['restore']} red={r['red']}"
    + (f" error={r['error']}" if r["error"] else "") for r in results)
summary = (f"{caught_n}/{len(CASES)} CAUGHT  restore={restored_n}/{len(CASES)}  "
           f"did_not_run={not_run_n}  clean_rerun={'GREEN' if clean else 'RED'}  {verdict}")
(HERE / "mutation_foe_build.log").write_text(body + f"\n\n{summary}\n", encoding="utf-8")
(HERE / "mutation_foe_build_result.json").write_text(
    json.dumps({"verdict": verdict, "cases": results, "clean": clean,
                "caught": caught_n, "restored": restored_n, "did_not_run": not_run_n},
               ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n{summary}")
raise SystemExit(0 if verdict == "MUTATION_FOE_BUILD_OK" else 1)
