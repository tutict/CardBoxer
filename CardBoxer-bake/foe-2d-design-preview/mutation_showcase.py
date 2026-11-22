"""展示层判据的变异验证：证明 9 条判据不是真空通过。

纪律：逐字节还原用 sha256 证明；锚点失配报 DID NOT RUN 并计入未证明；
每条点名一条应保持绿色的哨兵；跑完 clean re-run 必须全绿。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERIFY = HERE / "verify_showcase.py"
LOG = HERE / "verify_showcase.log"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_verify() -> dict:
    p = subprocess.run([sys.executable, str(VERIFY)], capture_output=True, text=True)
    lines = [x for x in LOG.read_text(encoding="utf-8").splitlines()
             if x.startswith(("PASS", "FAIL"))]
    return {"exit": p.returncode,
            "red": [x.split()[1] for x in lines if x.startswith("FAIL")],
            "green": {x.split()[1] for x in lines if x.startswith("PASS")}}


def enc(s: str) -> bytes:
    """needle 是 bytes；中文一律走 UTF-8 编码，别在 bytes 字面量里写 \\u
    —— bytes 不解析 \\u，会变成字面反斜杠序列，锚点静默失配。"""
    return s.encode("utf-8")


CASES = [
    {
        "name": "M1", "desc": "查看器里把一个 img src 改成不存在的文件",
        "target": "all_img_src_exist_and_relative",
        "sentinel": "copies_match_sources_byte_for_byte",
        "path": HERE / "foe-V1-2D-design-viewer.html",
        "old": enc('"file": "foe-V1-2D-design-board.png"'),
        "new": b'"file": "does-not-exist.png"',
    },
    {
        "name": "M2", "desc": "把「原图逐字节复制」换成另一张图的字节",
        "target": "copies_match_sources_byte_for_byte",
        "sentinel": "html_exists_and_offline",
        "path": HERE / "foe-full-original.png",
        "replace_with": HERE / "foe-redraw.png",
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
verdict = ("MUTATION_SHOWCASE_OK"
           if caught_n == len(CASES) and restored_n == len(CASES)
           and not_run_n == 0 and clean
           else "MUTATION_SHOWCASE_FAILED")
body = "\n".join(
    f"{r['name']} {'DID NOT RUN' if r['did_not_run'] else 'CAUGHT' if r['caught'] else 'MISSED!'}  "
    f"target_red={r['target_red']} sentinel_green={r['sentinel_green']} "
    f"restore={r['restore']} red={r['red']}"
    + (f" error={r['error']}" if r["error"] else "") for r in results)
summary = (f"{caught_n}/{len(CASES)} CAUGHT  restore={restored_n}/{len(CASES)}  "
           f"did_not_run={not_run_n}  clean_rerun={'GREEN' if clean else 'RED'}  {verdict}")
(HERE / "mutation_showcase.log").write_text(body + f"\n\n{summary}\n", encoding="utf-8")
(HERE / "mutation_showcase_result.json").write_text(
    json.dumps({"verdict": verdict, "cases": results, "clean": clean,
                "caught": caught_n, "restored": restored_n, "did_not_run": not_run_n},
               ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n{summary}")
raise SystemExit(0 if verdict == "MUTATION_SHOWCASE_OK" else 1)
