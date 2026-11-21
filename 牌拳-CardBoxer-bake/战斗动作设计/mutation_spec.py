"""变异验证：确认 13 条判据有牙，尤其防「空集真空通过」。

沿用既有纪律：锚点失配 = DID NOT RUN 并计入未证明；
还原按 sha256 逐字节证明，不用文本读写（Windows 会换换行）；
禁写字节码，避免陈旧 pyc 让变异没真正执行。
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
VERIFY = HERE / "verify_spec.py"

CASES = [
    ("M1", "battle_motion_spec.json",
     b'"reveal_seconds": 1.5', b'"reveal_seconds": 2.5',
     "constants_match_arena_source", "card_type_binding_and_damage_tiers_match_rules",
     "把亮牌阶段时长改成与 arena.gd 不符的 2.5s"),
    ("M2", "battle_motion_spec.json",
     b'"winner_asset": "reuse:card:wave"', b'"winner_asset": "reuse:card:wave_missing"',
     "reuse_assets_exist", "timeline_fully_covers_phases",
     "把三同赢家动作指向不存在的卡轨道"),
    ("M3", "battle_motion_spec.json",
     b'"actors": "winner"', b'"actors": "both"',
     "winner_attack_only_in_resolve", "constants_match_arena_source",
     "删掉唯一的赢家事件，试探空集真空通过"),
    ("M4", "源码基线.json",
     b"41e07b98", b"41e07b99",
     "game_sources_untouched", "phases_all_covered",
     "篡改源码基线指纹，假装源码没动"),
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
          f"sentinel_green={sentinel in green} restore={restored}  {desc}", flush=True)

all_restored = all(sha((HERE / n).read_bytes()) == sha(b) for n, b in orig.items())
code, red, _ = run_verify()
clean = code == 0 and not red
caught = sum(1 for r in results if r["caught"])
did_not_run = sum(1 for r in results if r["did_not_run"])
restored = sum(1 for r in results if r["restore"])
ok = (caught == len(CASES) and did_not_run == 0 and restored == len(CASES)
      and all_restored and clean)
verdict = "MUTATION_SPEC_OK" if ok else "MUTATION_SPEC_FAILED"
print(f"\nclean_rerun={'GREEN' if clean else 'RED'}  exit={code}  red={sorted(red)}", flush=True)
print(f"{caught}/{len(CASES)} CAUGHT  restore={restored}/{len(CASES)}  "
      f"did_not_run={did_not_run}  all_restored={all_restored}  {verdict}", flush=True)
(HERE / "mutation_spec_result.json").write_text(
    json.dumps({"verdict": verdict, "cases": results, "clean": clean,
                "caught": caught, "restored": restored,
                "did_not_run": did_not_run, "all_restored": all_restored},
               ensure_ascii=False, indent=2), encoding="utf-8")
sys.exit(0 if ok else 1)
