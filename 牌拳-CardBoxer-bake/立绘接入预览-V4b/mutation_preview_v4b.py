"""V4b 接入预览判据的变异验证。

纪律：
  * 变异体逐字节还原，用 sha256 证明，不用文本读写（会做换行转换）。
  * 每条变异点名一条「应当保持绿色」的哨兵判据，防止守卫整体崩掉造成假红。
  * 跑完必须 clean re-run 全绿，否则本轮不算证明。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
V3_PREVIEW = BAKE / "立绘接入预览"
VERIFY = HERE / "verify_preview_v4b.py"
LOG = HERE / "verify_preview_v4b.log"
SCRIPT = HERE / "make_preview_v4b.py"
MANIFEST = HERE / "preview_manifest.json"
A_IMG = HERE / "预览-A-战斗区替换.png"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_verify() -> dict:
    p = subprocess.run([sys.executable, str(VERIFY)], capture_output=True, text=True)
    lines = [x for x in LOG.read_text(encoding="utf-8").splitlines() if x.startswith(("PASS", "FAIL"))]
    red = [x.split()[1] for x in lines if x.startswith("FAIL")]
    green = {x.split()[1] for x in lines if x.startswith("PASS")}
    return {"exit": p.returncode, "red": red, "green": green}


def mutate_bytes(path: Path, old: bytes, new: bytes) -> tuple[bytes, str]:
    """二进制替换；返回原始字节 + 原始 sha。调用方负责逐字节还原。"""
    raw = path.read_bytes()
    assert old in raw, f"锚点失配: {path.name} 找不到 {old[:60]!r}"
    assert raw.count(old) == 1, f"锚点不唯一: {path.name} count={raw.count(old)}"
    path.write_bytes(raw.replace(old, new, 1))
    return raw, sha(path)


def restore(path: Path, raw: bytes) -> bool:
    path.write_bytes(raw)
    return sha(path) == hashlib.sha256(raw).hexdigest()


CASES = [
    {
        "name": "M1",
        "desc": "擦除填充源改回外侧 ±190（会复制斜向装饰）",
        "target": "erase_fill_uses_clean_center_patch",
        "sentinel": "manifest_erase_boxes_match_script",
        "path": SCRIPT,
        "old": b"erase_by_shift(img, (330, 310, 530, GROUND_Y - 2), 230)",
        "new": b"erase_by_shift(img, (330, 310, 530, GROUND_Y - 2), -190)",
    },
    {
        "name": "M2",
        "desc": "SUBJECT.front 换成 V3 的窄包围盒（照抄旧模型）",
        "target": "subject_bbox_matches_measured_probe",
        "sentinel": "geometry_matches_game_source",
        "path": SCRIPT,
        "old": b'"front": (174, 96, 594, 672),',
        "new": b'"front": (265, 96, 503, 672),',
    },
    {
        "name": "M3",
        "desc": "A 图换成 V3 版副本（拿旧造型冒充 V4b）",
        "target": "not_a_copy_of_v3_preview",
        "sentinel": "outputs_exist_and_1280x720",
        "path": A_IMG,
        "old": None,  # 整文件替换，走专用分支
        "new": None,
    },
    {
        "name": "M4",
        "desc": "manifest 里脸特写母图的 sha 改错（假装换了母图不认账）",
        "target": "face_source_sha_matches_manifest",
        "sentinel": "v4b_source_sha_matches_manifest",
        "path": MANIFEST,
        "old": None,
        "new": None,
    },
]

results = []
for c in CASES:
    path: Path = c["path"]
    original = path.read_bytes()
    original_sha = hashlib.sha256(original).hexdigest()
    try:
        if c["name"] == "M3":
            with open(V3_PREVIEW / A_IMG.name, "rb") as f:
                path.write_bytes(f.read())
        elif c["name"] == "M4":
            man = json.loads(original.decode("utf-8"))
            k = sorted(man["face_sources"])[0]
            man["face_sources"][k] = "0" * 64
            path.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            assert c["old"] in original, f"{c['name']} 锚点失配"
            assert original.count(c["old"]) == 1, f"{c['name']} 锚点不唯一"
            path.write_bytes(original.replace(c["old"], c["new"], 1))

        mutated_sha = sha(path)
        assert mutated_sha != original_sha, f"{c['name']} 变异没改变字节"
        r = run_verify()
        target_red = c["target"] in r["red"]
        sentinel_green = c["sentinel"] in r["green"]
        caught = bool(r["exit"] != 0 and target_red and sentinel_green)
        results.append({
            "name": c["name"], "caught": caught, "target_red": target_red,
            "sentinel_green": sentinel_green, "red": r["red"],
        })
    finally:
        path.write_bytes(original)

    ok = sha(path) == original_sha
    results[-1]["restore"] = ok
    print(f"{c['name']} {'CAUGHT' if results[-1]['caught'] else 'MISSED!'}  "
          f"red={target_red} sentinel_green={sentinel_green} "
          f"restore={ok}  {c['desc']}", flush=True)

final = run_verify()
clean = final["exit"] == 0 and not final["red"]
caught_n = sum(1 for r in results if r["caught"])
restored_n = sum(1 for r in results if r["restore"])
verdict = "MUTATION_V4B_OK" if (caught_n == len(CASES) and restored_n == len(CASES) and clean) else "MUTATION_V4B_FAILED"
summary = (f"\n{caught_n}/{len(CASES)} CAUGHT  restore={restored_n}/{len(CASES)}  "
           f"clean_rerun={'GREEN' if clean else 'RED'}  {verdict}\n")
(HERE / "mutation_preview_v4b.log").write_text(
    "\n".join(f"{r['name']} {'CAUGHT' if r['caught'] else 'MISSED!'}  "
              f"target_red={r['target_red']} sentinel_green={r['sentinel_green']} "
              f"restore={r['restore']} red={r['red']}" for r in results) + summary,
    encoding="utf-8")
(HERE / "mutation_preview_v4b_result.json").write_text(
    json.dumps({"verdict": verdict, "cases": results, "clean": clean}, ensure_ascii=False, indent=2),
    encoding="utf-8")
print(summary)
raise SystemExit(0 if verdict == "MUTATION_V4B_OK" else 1)
