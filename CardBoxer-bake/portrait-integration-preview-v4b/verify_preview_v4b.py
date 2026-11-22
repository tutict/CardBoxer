"""V4b 定稿造型接入预览的承重判据。

只证明「贴片按源码几何落到位、素材确实是 V4b、没碰别的地方」，
不证明好看、不证明能进引擎、不证明有动作帧 —— 那些只能靠看图。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
V3_PREVIEW = BAKE / "portrait-integration-preview"
MANIFEST = HERE / "preview_manifest.json"
SCRIPT = HERE / "make_preview_v4b.py"

sys.path.insert(0, str(HERE))
from make_preview_v4b import (  # noqa: E402
    CARD_GAP, CARD_H, CARD_W, COOL, FACE_SHOT, HAND_Y, SUBJECT, WARM,
    char_card, portrait_crop,
)

SHOT = BAKE / "background-candidates" / "rage-meter" / "rage-meter-full-meter.png"
NAMES = {
    "A": "preview-A-arena-replacement.png",
    "B": "preview-B-card-art-and-avatars.png",
    "C": "preview-C-character-profile.png",
    "D": "preview-D-part-size-samples.png",
    "E": "preview-overview.png",
}

# V4b 立绘更宽：擦除框 (330..530) / (750..950)，贴片 top=280，标记框不变
A_ALLOWED = [(330, 280, 530, 520), (750, 280, 950, 520), (16, 626, 234, 666)]
X0 = 640 - (5 * CARD_W + 4 * CARD_GAP) // 2
B_ALLOWED = [
    (X0, HAND_Y, X0 + CARD_W, HAND_Y + CARD_H),
    (X0 + 4 * (CARD_W + CARD_GAP), HAND_Y, X0 + 4 * (CARD_W + CARD_GAP) + CARD_W, HAND_Y + CARD_H),
    (0, 0, 46, 46),
    (1232, 0, 1280, 46),
    (16, 626, 234, 666),
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def diff_count(a: Image.Image, b: Image.Image, box=None, tol: int = 6) -> int:
    if box:
        a, b = a.crop(box), b.crop(box)
    d = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    return d.point(lambda v: 255 if v > tol else 0).histogram()[255]


def outside_diff(a: Image.Image, b: Image.Image, allowed, tol: int = 6) -> int:
    mask = Image.new("L", a.size, 255)
    d = ImageDraw.Draw(mask)
    for box in allowed:
        d.rectangle(box, fill=0)
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L")
    diff = diff.point(lambda v: 255 if v > tol else 0)
    return ImageChops.multiply(diff, mask).histogram()[255]


def color_variety(im: Image.Image) -> int:
    small = im.convert("RGB").resize((160, 90), Image.Resampling.BILINEAR)
    return len(set(small.get_flattened_data() if hasattr(small, "get_flattened_data") else small.getdata()))


def source_constants() -> dict:
    arena = (GAME / "scripts" / "arena.gd").read_text(encoding="utf-8")
    hud = (GAME / "scripts" / "hud.gd").read_text(encoding="utf-8")

    def grab(text: str, name: str) -> float:
        m = re.search(rf"const {name} := (\d+\.?\d*)", text)
        if not m:
            raise AssertionError(f"源码里找不到 const {name}")
        return float(m.group(1))

    def pos_x(text: str, who: str) -> float:
        m = re.search(rf"{who}\.position = Vector2\((\d+), GROUND_Y\)", text)
        if not m:
            raise AssertionError(f"源码里找不到 {who}.position")
        return float(m.group(1))

    return {
        "arena.gd": {"GROUND_Y": grab(arena, "GROUND_Y"), "player_x": pos_x(arena, "player"), "enemy_x": pos_x(arena, "enemy")},
        "hud.gd": {k: grab(hud, k) for k in ("CARD_W", "CARD_H", "CARD_GAP", "HAND_Y")},
    }


def main() -> None:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok), detail))

    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with Image.open(SHOT) as s:
        shot = s.convert("RGB")
    imgs = {}
    for k, fn in NAMES.items():
        with Image.open(HERE / fn) as f:
            imgs[k] = f.convert("RGB")

    # 1 五张图都在、尺寸对、非空白
    check("outputs_exist_and_1280x720",
          all(v.size == (1280, 720) for v in imgs.values()),
          str({k: v.size for k, v in imgs.items()}))
    varieties = {k: color_variety(v) for k, v in imgs.items()}
    check("outputs_not_blank", all(n > 400 for n in varieties.values()), str(varieties))

    # 2 输出 sha 与 manifest 一致
    check("output_sha_matches_manifest",
          all(sha256(HERE / man["outputs"][k]["file"]) == man["outputs"][k]["sha256"] for k in NAMES))
    check("source_shot_sha_matches_manifest", sha256(SHOT) == man["source_shot_sha256"])

    # 3 几何常量从游戏源码读出对上
    src = source_constants()
    check("geometry_matches_game_source", src == man["geometry_from_source"],
          f"source={src} manifest={man['geometry_from_source']}")
    check("geometry_matches_script_constants",
          src["hud.gd"] == {"CARD_W": CARD_W, "CARD_H": CARD_H, "CARD_GAP": CARD_GAP, "HAND_Y": HAND_Y})

    # 4 A：改动只落在两个贴片/擦除框 + 标记框
    outside_a = outside_diff(imgs["A"], shot, A_ALLOWED)
    check("a_no_changes_outside_subject_boxes", outside_a == 0, f"outside_px={outside_a}")
    changed_a = diff_count(imgs["A"], shot, (390, 300, 470, 500))
    check("a_subject_region_actually_replaced", changed_a > 5000, f"changed_px={changed_a}")
    check("a_hud_untouched", diff_count(imgs["A"], shot, (0, 0, 1280, 120)) == 0)
    check("a_cards_untouched", diff_count(imgs["A"], shot, (238, 552, 1042, 702)) == 0)

    # 5 B：只换卡 1 / 卡 5 + 头像 + 标记，中间三张逐像素原样
    outside_b = outside_diff(imgs["B"], shot, B_ALLOWED)
    check("b_no_changes_outside_allowed_boxes", outside_b == 0, f"outside_px={outside_b}")
    unchanged_cards = [diff_count(imgs["B"], shot, (X0 + i * (CARD_W + CARD_GAP), HAND_Y,
                                                    X0 + i * (CARD_W + CARD_GAP) + CARD_W, HAND_Y + CARD_H))
                       for i in (1, 2, 3)]
    check("b_middle_three_cards_pixel_identical", all(v == 0 for v in unchanged_cards), str(unchanged_cards))
    changed_b1 = diff_count(imgs["B"], shot, (X0, HAND_Y, X0 + CARD_W, HAND_Y + CARD_H))
    c5x = X0 + 4 * (CARD_W + CARD_GAP)
    changed_b5 = diff_count(imgs["B"], shot, (c5x, HAND_Y, c5x + CARD_W, HAND_Y + CARD_H))
    check("b_card1_and_card5_actually_replaced", changed_b1 > 4000 and changed_b5 > 4000,
          f"card1={changed_b1} card5={changed_b5}")

    # 6 卡面是脚本当场重算出来的
    c1 = imgs["B"].crop((X0, HAND_Y, X0 + CARD_W, HAND_Y + CARD_H))
    c5 = imgs["B"].crop((c5x, HAND_Y, c5x + CARD_W, HAND_Y + CARD_H))
    check("b_card_matches_recomputed_asset",
          diff_count(c1, char_card("front", 1, "裁决官", "", WARM)) == 0
          and diff_count(c5, char_card("angle25", 5, "青岚", "", COOL)) == 0)

    check("offline_tag_does_not_overlap_card1", 234 < X0, f"tag_right=234 card1_left={X0}")

    # 7 V4b 专属：擦除填充源必须取自两人之间 x=560..760 的干净背景。
    # 从脚本里正则提 (box, dx)，可复算，不写死数字。
    text = SCRIPT.read_text(encoding="utf-8")
    calls = re.findall(
        r"erase_by_shift\(img,\s*\((\d+),\s*(\d+),\s*(\d+),\s*GROUND_Y - 2\),\s*(-?\d+)\)", text)
    sources = [(int(x0) + int(dx), int(x1) + int(dx)) for x0, _, x1, dx in calls]
    check("erase_fill_uses_clean_center_patch",
          len(sources) == 2 and all(s == (560, 760) for s in sources),
          f"erase_calls={len(calls)} source_x_ranges={sources}")
    check("manifest_erase_boxes_match_script",
          man["composite"]["erase_boxes"] == [[int(x0), int(y0), int(x1), 518] for x0, y0, x1, _ in calls],
          str(man["composite"]["erase_boxes"]))

    # 8 V4b 素材：四视角 + 脸特写的 sha 都要对得上，且 SUBJECT 来自实测探针
    probe = json.loads((HERE / "probe_v4b_assets.json").read_text(encoding="utf-8"))
    measured = {k: tuple(v) for k, v in probe["suggested_subject"].items()}
    check("subject_bbox_matches_measured_probe",
          {k: tuple(v) for k, v in SUBJECT.items()} == measured, str(measured))
    check("v4b_source_sha_matches_manifest",
          all(sha256(BAKE / "3d-model-probe-v4b" / fn) == h for fn, h in man["sources"].items()),
          f"sources={len(man['sources'])}")
    check("face_source_sha_matches_manifest",
          all(sha256(BAKE / "3d-model-probe-v4b" / fn) == h for fn, h in man["face_sources"].items()),
          f"face_sources={list(man['face_sources'])}")
    check("face_shot_mapping_is_wired",
          set(FACE_SHOT.values()) == set(man["face_sources"]), str(FACE_SHOT))
    face = portrait_crop("front")
    corners = [face.getpixel(p)[3] for p in ((0, 0), (599, 0), (0, 599), (599, 599))]
    check("avatar_mother_is_600px_transparent_face_shot",
          face.size == (600, 600) and all(a == 0 for a in corners),
          f"size={face.size} corner_alpha={corners}")

    # 9 不能是 V3 版旧图复制过来冒充
    diffs = {}
    for k in ("A", "B", "D"):
        with Image.open(V3_PREVIEW / NAMES[k]) as f:
            old = f.convert("RGB")
        diffs[k] = diff_count(imgs[k], old)
    check("not_a_copy_of_v3_preview", all(v > 12000 for v in diffs.values()), str(diffs))

    # 10 游戏源码零改动
    marker = SCRIPT.stat().st_mtime
    newer = [str(p.relative_to(GAME)) for p in GAME.rglob("*")
             if p.is_file() and ".godot" not in p.parts and p.stat().st_mtime > marker]
    check("game_sources_not_modified", not newer, f"newer_files={newer[:8]}")

    passed = sum(1 for _, ok, _ in checks if ok)
    lines = [f"{'PASS' if ok else 'FAIL'}  {name}  {detail}" for name, ok, detail in checks]
    verdict = "PREVIEW_V4B_VERIFIED" if passed == len(checks) else "PREVIEW_V4B_CHECK_FAILED"
    text_out = "\n".join(lines) + f"\n\n{passed}/{len(checks)} PASS  {verdict}\n"
    (HERE / "verify_preview_v4b.log").write_text(text_out, encoding="utf-8")
    (HERE / "verify_preview_v4b_result.json").write_text(
        json.dumps({"verdict": verdict, "passed": passed, "total": len(checks),
                    "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(text_out)
    raise SystemExit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
