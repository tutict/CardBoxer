"""对手怪概念阶段判据的变异验证。

纪律：逐字节还原用 sha256 证明；每条点名一条应保持绿色的哨兵；
跑完 clean re-run 必须全绿。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONCEPT = HERE / "概念图"
VERIFY = HERE / "verify_concept.py"
LOG = HERE / "verify_concept.log"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_verify() -> dict:
    p = subprocess.run([sys.executable, str(VERIFY)], capture_output=True, text=True)
    lines = [x for x in LOG.read_text(encoding="utf-8").splitlines()
             if x.startswith(("PASS", "FAIL"))]
    return {
        "exit": p.returncode,
        "red": [x.split()[1] for x in lines if x.startswith("FAIL")],
        "green": {x.split()[1] for x in lines if x.startswith("PASS")},
    }


CASES = [
    {
        "name": "M1", "desc": "prompt.txt 改一个词（规格与校验不再自洽）",
        "target": "prompt_ok_and_sha_self_consistent",
        "sentinel": "quota_429_recorded_no_fake_artifacts",
        "path": HERE / "prompt.txt",
        "old": b"bulky androgynous armored scavenger raider",
        "new": b"slim unarmored ordinary civilian bystander",
    },
    {
        "name": "M2", "desc": "gen_stdout.json 的 429 改成 200（假装生成成功）",
        "target": "quota_429_recorded_no_fake_artifacts",
        "sentinel": "two_concept_images_valid",
        "path": HERE / "gen_stdout.json",
        "old": b'"http_status": 429',
        "new": b'"http_status": 200',
    },
    {
        "name": "M3", "desc": "对照板换成概念图副本（尺寸不对）",
        "target": "concept_board_valid",
        "sentinel": "board_bboxes_are_measured_not_guessed",
        "path": HERE / "玩家V4b-对手怪V1-概念对照.png",
        "replace_with": CONCEPT / "Full_body_character_concept_ar_2026-11-07T11-02-32.png",
    },
    {
        "name": "M4", "desc": "对照板 stats 的玩家 bbox 改错一个坐标（假装有实测）",
        "target": "board_bboxes_are_measured_not_guessed",
        "sentinel": "concept_board_valid",
        "path": CONCEPT / "concept_compare_stats.json",
        # stats 由 json.dumps(indent=2) 写出：数组逐行展开，且 Windows 下是 CRLF。
        # 首次 M4 用单行 b'"player_bbox_in_source": [174, ...]' 做 needle，
        # 匹配 0 次直接把脚本崩在半路（见 mutation_run.log）。改用不含换行的
        # 单行元素 needle，避开行尾口径；改一个坐标足以让实测对账判据报红。
        "old": b"    174,",
        "new": b"    1,",
    },
]

results = []
for c in CASES:
    path: Path = c["path"]
    original = path.read_bytes()
    original_sha = hashlib.sha256(original).hexdigest()
    # 锚点失配 = DID NOT RUN，必须计入「未证明」，不能崩在半路只留半张汇总。
    # 首次 M4 就是 assert 直接抛出，导致 clean re-run 根本没跑、盘上
    # verify_concept.log 停在 M3 变异中间态（9/10 FAIL）—— 比没汇总更坏。
    rec = {"name": c["name"], "caught": False, "target_red": False,
           "sentinel_green": False, "red": [], "did_not_run": False,
           "restore": False, "error": ""}
    results.append(rec)
    try:
        if "replace_with" in c:
            path.write_bytes(Path(c["replace_with"]).read_bytes())
        else:
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
verdict = ("MUTATION_CONCEPT_OK"
           if caught_n == len(CASES) and restored_n == len(CASES)
           and not_run_n == 0 and clean
           else "MUTATION_CONCEPT_FAILED")
body = "\n".join(
    f"{r['name']} {'DID NOT RUN' if r['did_not_run'] else 'CAUGHT' if r['caught'] else 'MISSED!'}  "
    f"target_red={r['target_red']} sentinel_green={r['sentinel_green']} "
    f"restore={r['restore']} red={r['red']}"
    + (f" error={r['error']}" if r["error"] else "") for r in results)
summary = (f"{caught_n}/{len(CASES)} CAUGHT  restore={restored_n}/{len(CASES)}  "
           f"did_not_run={not_run_n}  clean_rerun={'GREEN' if clean else 'RED'}  {verdict}")
(HERE / "mutation_concept.log").write_text(body + f"\n\n{summary}\n", encoding="utf-8")
(HERE / "mutation_concept_result.json").write_text(
    json.dumps({"verdict": verdict, "cases": results, "clean": clean,
                "caught": caught_n, "restored": restored_n, "did_not_run": not_run_n},
               ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n{summary}")
raise SystemExit(0 if verdict == "MUTATION_CONCEPT_OK" else 1)
