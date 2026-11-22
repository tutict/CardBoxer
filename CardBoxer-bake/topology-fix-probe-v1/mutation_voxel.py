"""变异验证：确认 14 条判据真的有牙，不是真空通过。

沿用上一轮教训：锚点失配 = DID NOT RUN 并计入未证明，不崩在半路；
还原必须按 sha256 逐字节证明，不能用文本读写（Windows 会换换行）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV_PY = Path(r"C:\Users\tutic\IdeaProjects\Fantasy-Agent\.venv\Scripts\python.exe")
VERIFY = HERE / "verify_voxel.py"

CASES = [
    ("M1", "voxel_probe.json",
     b'"coverage": 0.0', b'"coverage": 1.0',
     "baseline_bone_heat_really_zero", "voxel_035_autoweight_full",
     "把基线的 Bone Heat 0 覆盖伪装成 1.0"),
    ("M2", "transfer_probe.json",
     b'"textures_same_as_source": true', b'"textures_same_as_source": false',
     "transfer_keeps_original_assets", "transfer_reduces_max_displacement",
     "把 PBR 贴图保住伪装成丢失"),
    ("M3", "transfer_probe.json",
     b'"max_displacement_m": 0.39142', b'"max_displacement_m": 0.99142',
     "transfer_reduces_max_displacement", "transfer_spreads_influence",
     "把 B 的最大位移改到比 A 还大"),
    ("M4", "topology-fix-probe-conclusion.txt",
     "右臂都不可见".encode("utf-8"), "右臂完整可见".encode("utf-8"),
     "negative_result_not_hidden", "source_blend_unchanged",
     "把看图负结果改写成通过"),
]

env = dict(os.environ)
env["PYTHONDONTWRITEBYTECODE"] = "1"

orig = {name: (HERE / name).read_bytes()
        for name in sorted({c[1] for c in CASES})}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def run_verify():
    p = subprocess.run([str(VENV_PY), "-u", str(VERIFY)],
                       cwd=str(HERE), env=env, capture_output=True, text=True)
    red = set(re.findall(r"^FAIL\s+(\S+)", p.stdout, re.M))
    green = set(re.findall(r"^PASS\s+(\S+)", p.stdout, re.M))
    return p.returncode, red, green, p.stdout + p.stderr


results = []
for tag, fname, needle, mutant, target, sentinel, desc in CASES:
    fp = HERE / fname
    before = orig[fname]
    n = before.count(needle)
    if n != 1:
        results.append({"tag": tag, "caught": False, "did_not_run": True,
                        "restore": True, "error": f"anchor matched {n} times",
                        "desc": desc})
        print(f"{tag} DID NOT RUN  anchor_count={n}  {desc}  [锚点失配]", flush=True)
        continue

    fp.write_bytes(before.replace(needle, mutant, 1))
    code, red, green, out = run_verify()
    caught = (target in red and sentinel in green)
    fp.write_bytes(before)
    restored = sha(fp.read_bytes()) == sha(before)
    results.append({"tag": tag, "caught": caught, "did_not_run": False,
                    "restore": restored, "target_red": target in red,
                    "sentinel_green": sentinel in green,
                    "red": sorted(red), "error": "", "desc": desc})
    print(f"{tag} {'CAUGHT' if caught else 'MISSED'}  target_red={target in red} "
          f"sentinel_green={sentinel in green} restore={restored}  {desc}", flush=True)

# clean re-run：所有文件还原后必须全绿
all_restored = all(sha((HERE / n).read_bytes()) == sha(b) for n, b in orig.items())
code, red, green, clean_out = run_verify()
clean = (code == 0 and not red)
print(f"\nclean_rerun={'GREEN' if clean else 'RED'}  exit={code}  red={sorted(red)}",
      flush=True)

caught = sum(1 for r in results if r["caught"])
did_not_run = sum(1 for r in results if r["did_not_run"])
restored = sum(1 for r in results if r["restore"])
ok = (caught == len(CASES) and did_not_run == 0
      and restored == len(CASES) and all_restored and clean)
verdict = "MUTATION_VOXEL_OK" if ok else "MUTATION_VOXEL_FAILED"
print(f"\n{caught}/{len(CASES)} CAUGHT  restore={restored}/{len(CASES)}  "
      f"did_not_run={did_not_run}  all_restored={all_restored}  {verdict}", flush=True)

(HERE / "mutation_voxel_result.json").write_text(
    json.dumps({"verdict": verdict, "cases": results, "clean": clean,
                "caught": caught, "restored": restored,
                "did_not_run": did_not_run, "all_restored": all_restored},
               ensure_ascii=False, indent=2), encoding="utf-8")
sys.exit(0 if ok else 1)
