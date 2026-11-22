"""变异验证：故意改坏产物，确认 verify_preview.py 的关键判据真的会红。

纪律：
  * 逐字节备份 / 还原，用 sha256 证明还原成功，不用文本模式读写。
  * 每个变异体必须语法/文件结构成立；这里全是 PNG / JSON，不会因"文件坏了"报红。
  * 除了目标判据，还要点名一条应保持绿色的哨兵判据，防止靠无关假红蒙混。
  * 跑完必须 clean re-run 并证明 16/16 全绿，才把结果记为 CAUGHT。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
SHOT = BAKE / "background-candidates" / "rage-meter" / "rage-meter-full-meter.png"
VERIFY = HERE / "verify_preview.py"
RESULT = HERE / "verify_preview_result.json"
MANIFEST = HERE / "preview_manifest.json"
A_IMG = HERE / "preview-A-arena-replacement.png"
B_IMG = HERE / "preview-B-card-art-and-avatars.png"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_verify() -> dict:
    subprocess.run([sys.executable, str(VERIFY)], capture_output=True, text=True)
    return json.loads(RESULT.read_text(encoding="utf-8"))


def status(res: dict, name: str) -> bool:
    return next(c["ok"] for c in res["checks"] if c["name"] == name)


def paint(path: Path, box, color) -> None:
    with Image.open(path) as f:
        im = f.convert("RGB")
    ImageDraw.Draw(im).rectangle(box, fill=color)
    im.save(path)


CASES = [
    {
        "id": "M1",
        "desc": "A 图换成原截帧（角色根本没换）",
        "file": A_IMG,
        "mutate": lambda p: (lambda im: im.save(p))(Image.open(SHOT).convert("RGB")),
        "expect_red": "a_subject_region_actually_replaced",
        "sentinel_green": "outputs_not_blank",
    },
    {
        "id": "M2",
        "desc": "B 图第 2 张卡被涂改（越界改动）",
        "file": B_IMG,
        "mutate": lambda p: paint(p, (420, 570, 445, 595), (240, 40, 40)),
        "expect_red": "b_middle_three_cards_pixel_identical",
        "sentinel_green": "b_card1_and_card5_actually_replaced",
    },
    {
        "id": "M3",
        "desc": "manifest 里 CARD_W 改成 200（几何过期）",
        "file": MANIFEST,
        "mutate": lambda p: p.write_text(
            json.dumps({**json.loads(p.read_text(encoding="utf-8")),
                        "geometry_from_source": {
                            **json.loads(p.read_text(encoding="utf-8"))["geometry_from_source"],
                            "hud.gd": {**json.loads(p.read_text(encoding="utf-8"))["geometry_from_source"]["hud.gd"],
                                       "CARD_W": 200}}},
                       ensure_ascii=False, indent=2), encoding="utf-8"),
        "expect_red": "geometry_matches_game_source",
        "sentinel_green": "output_sha_matches_manifest",
    },
    {
        "id": "M4",
        "desc": "A 图顶部 HUD 被涂改（越界改动）",
        "file": A_IMG,
        "mutate": lambda p: paint(p, (100, 50, 114, 64), (255, 255, 255)),
        "expect_red": "a_hud_untouched",
        "sentinel_green": "a_subject_region_actually_replaced",
    },
]


def main() -> None:
    rows = []
    for case in CASES:
        target = case["file"]
        original = target.read_bytes()
        original_sha = sha(target)
        try:
            case["mutate"](target)
            res = run_verify()
            red = not status(res, case["expect_red"])
            green = status(res, case["sentinel_green"])
            verdict = "CAUGHT" if (red and green) else "MISSED"
            rows.append({
                "id": case["id"], "desc": case["desc"], "verdict": verdict,
                "target_red": case["expect_red"], "target_was_red": red,
                "sentinel": case["sentinel_green"], "sentinel_was_green": green,
                "total_passed": res["passed"],
            })
        finally:
            target.write_bytes(original)
        restored = sha(target) == original_sha
        rows[-1]["restored_sha_ok"] = restored
        if not restored:
            rows[-1]["verdict"] = "RESTORE_FAILED"
        print(f"{case['id']} {rows[-1]['verdict']}  red={red} green={green} restore={restored}")

    clean = run_verify()
    clean_ok = clean["verdict"] == "PREVIEW_VERIFIED" and clean["passed"] == clean["total"]
    caught = sum(1 for r in rows if r["verdict"] == "CAUGHT")
    text = json.dumps({"cases": rows, "caught": caught, "total": len(rows),
                       "clean_rerun": clean_ok, "clean_passed": clean["passed"],
                       "verdict": "MUTATION_OK" if caught == len(rows) and clean_ok else "MUTATION_FAILED"},
                      ensure_ascii=False, indent=2)
    (HERE / "mutation_preview_result.json").write_text(text + "\n", encoding="utf-8")
    (HERE / "mutation_preview.log").write_text(
        "\n".join(f"{r['id']} {r['verdict']}  {r['desc']}  red={r['target_was_red']} "
                  f"sentinel_green={r['sentinel_was_green']} restore={r['restored_sha_ok']}" for r in rows)
        + f"\n\n{caught}/{len(rows)} CAUGHT  clean_rerun={clean['passed']}/{clean['total']}\n",
        encoding="utf-8")
    print(text)
    raise SystemExit(0 if caught == len(rows) and clean_ok else 1)


if __name__ == "__main__":
    main()
