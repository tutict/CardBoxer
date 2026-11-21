"""变异验证：确认 15 条承重判据有牙，尤其防「锚点失配却照报 CAUGHT」。

纪律（沿用本项目既有做法）：
  * 二进制读写 + sha256 逐字节证明还原，不用文本模式（Windows 会换换行）；
  * 锚点匹配数 != 1 -> DID NOT RUN，计入未证明，不继续跑该 case；
  * 变异体必须语法/格式上仍成立（PNG 只坏魔数、JSON 只改一个值），
    证明的是判据能抓到，不是「文件彻底坏了」；
  * PYTHONDONTWRITEBYTECODE=1，防陈旧 pyc 让变异没真正执行；
  * 全部还原后 clean re-run 必须 15/15 GREEN。

自检模式：ATTACK3D_SELFTEST=1 时把 M1 锚点换成不存在的串，
应得到 did_not_run=1 且 verdict=FAILED（证明这条分支本身有牙）。
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
VERIFY = HERE / "verify_attack_3d.py"
SELFTEST = os.environ.get("ATTACK3D_SELFTEST") == "1"
RESULT_FILE = ("mutation_selftest_result.json" if SELFTEST
               else "mutation_attack_3d_result.json")

CASES = [
    ("M1", "frames/puppet_player/manifest.json",
     b'"stance_pixel_identical_to_source": true',
     b'"stance_pixel_identical_to_source": false',
     "stance_is_untouched_portrait", "joint_hashes_recomputed",
     "伪造站架帧不是原始 3D 立绘"),
    ("M2", "frames/puppet_player/stance_f000.png",
     b"\x89PNG\r\n\x1a\n", b"\x89PNG\r\n\x1a\x00",
     "png_bytes_and_hash", "boards_nonempty",
     "改坏一张帧 PNG 的文件魔数"),
    ("M3", "frames/foe/manifest.json",
     b'"mean_displacement_m": 0.26873', b'"mean_displacement_m": 0.0',
     "mesh_deform_falsified", "gifs_animated",
     "把网格撕裂的量化证据抹成 0"),
    ("M4", "apose_joints.json",
     b'"head": [384, 96],', b'"head": [384, 196],',
     "spec_mapping_table_consistency", "frame_counts_exact",
     "偷偷改 A-pose 头顶标定却不重算指纹"),
    ("M5", "make_puppet.py",
     b"wrap_pi(angle(fp[u], fp[v])", b"nowrap(angle(fp[u], fp[v])",
     "angle_wrap_wired_and_bounded", "single_arm_semantics",
     "摘掉角度环绕，试探 310 度翻臂能否蒙混过关"),
    ("M6", "../战斗动作设计/源码基线.json",
     b"41e07b98", b"41e07b99",
     "game_sources_untouched", "gifs_animated",
     "篡改源码基线指纹，假装游戏源码没动"),
]
if SELFTEST:
    tag, f, _n, m, t, s, d = CASES[0]
    CASES[0] = (tag, f, b"ANCHOR_THAT_DOES_NOT_EXIST_9999", m, t, s, d)

env = dict(os.environ)
env["PYTHONDONTWRITEBYTECODE"] = "1"
orig = {name: (HERE / name).read_bytes()
        for name in sorted({c[1] for c in CASES})}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def run_verify():
    p = subprocess.run([str(VENV_PY), "-u", str(VERIFY)],
                       cwd=str(HERE), env=env, capture_output=True, text=True)
    return (p.returncode,
            set(re.findall(r"^FAIL\s+(\S+)", p.stdout, re.M)),
            set(re.findall(r"^PASS\s+(\S+)", p.stdout, re.M)))


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
    _, red, green = run_verify()
    caught = target in red and sentinel in green
    fp.write_bytes(before)
    restored = sha(fp.read_bytes()) == sha(before)
    results.append({"tag": tag, "caught": caught, "did_not_run": False,
                    "restore": restored, "target_red": target in red,
                    "sentinel_green": sentinel in green,
                    "red": sorted(red), "error": "", "desc": desc})
    print(f"{tag} {'CAUGHT' if caught else 'MISSED'}  target_red={target in red} "
          f"sentinel_green={sentinel in green} restore={restored}  {desc}",
          flush=True)

all_restored = all(sha((HERE / n).read_bytes()) == sha(b) for n, b in orig.items())
code, red, _ = run_verify()
clean = code == 0 and not red
caught = sum(1 for r in results if r["caught"])
did_not_run = sum(1 for r in results if r["did_not_run"])
restored = sum(1 for r in results if r["restore"])

if SELFTEST:
    ok = did_not_run == 1 and all_restored and clean and caught == len(CASES) - 1
    verdict = "DID_NOT_RUN_SELFTEST_OK" if ok else "DID_NOT_RUN_SELFTEST_FAILED"
else:
    ok = (caught == len(CASES) and did_not_run == 0
          and restored == len(CASES) and all_restored and clean)
    verdict = "MUTATION_ATTACK_3D_OK" if ok else "MUTATION_ATTACK_3D_FAILED"

print(f"\nclean_rerun={'GREEN' if clean else 'RED'}  exit={code}  red={sorted(red)}",
      flush=True)
print(f"{caught}/{len(CASES)} CAUGHT  restore={restored}/{len(CASES)}  "
      f"did_not_run={did_not_run}  all_restored={all_restored}  {verdict}",
      flush=True)
(HERE / RESULT_FILE).write_text(json.dumps({
    "verdict": verdict, "selftest": SELFTEST, "cases": results, "clean": clean,
    "caught": caught, "restored": restored, "did_not_run": did_not_run,
    "all_restored": all_restored, "clean_red": sorted(red),
}, ensure_ascii=False, indent=2), encoding="utf-8")
sys.exit(0 if ok else 1)
