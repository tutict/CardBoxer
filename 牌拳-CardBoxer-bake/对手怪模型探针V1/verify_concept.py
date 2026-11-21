"""对手怪 V1（2D 概念阶段）的承重判据。

只证明「规格/prompt 自洽、配额阻塞被如实记录、概念图与对照板真在盘上、
游戏源码没动」。不证明造型好看、不证明 3D 模型存在、不证明能进引擎。
3D 产物出来后另由 inspect/measure_silhouette/verify 判。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "牌拳-CardBoxer"
CONCEPT = HERE / "概念图"
PLAYER = BAKE / "3D模型探针V4b" / "v4b-front.png"
C1 = CONCEPT / "Full_body_character_concept_ar_2026-11-07T11-02-32.png"
C2 = CONCEPT / "Same_single_character__identic_2026-11-07T11-03-25.png"
BOARD = HERE / "玩家V4b-对手怪V1-概念对照.png"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def nonblank(p: Path, size=None) -> tuple[bool, str]:
    with Image.open(p) as f:
        im = f.convert("RGB")
    small = im.resize((120, 120), Image.Resampling.BILINEAR)
    n = len(set(small.get_flattened_data() if hasattr(small, "get_flattened_data")
                else small.getdata()))
    return (n > 300 and (size is None or im.size == size)), f"{im.size} colors={n}"


def diff(a: Path, b: Path, tol: int = 8) -> int:
    with Image.open(a) as x, Image.open(b) as y:
        ia = x.convert("RGB").resize((256, 256), Image.Resampling.BILINEAR)
        ib = y.convert("RGB").resize((256, 256), Image.Resampling.BILINEAR)
    d = ImageChops.difference(ia, ib).convert("L")
    return d.point(lambda v: 255 if v > tol else 0).histogram()[255]


def lowfreq_mae(a: Path, b: Path) -> float:
    """缩到 16x16 后逐通道平均绝对差：只看构图 / 剪影 / 明暗布局，
    不吃金属划痕这类高频纹理。0-255 尺度上 <30 视为同一构图。
    用像素级差异判「同一角色」是错的 —— 图生图必然重绘纹理。"""
    with Image.open(a) as x, Image.open(b) as y:
        ia = x.convert("RGB").resize((16, 16), Image.Resampling.BILINEAR)
        ib = y.convert("RGB").resize((16, 16), Image.Resampling.BILINEAR)
    pa = list(ia.get_flattened_data() if hasattr(ia, "get_flattened_data") else ia.getdata())
    pb = list(ib.get_flattened_data() if hasattr(ib, "get_flattened_data") else ib.getdata())
    return round(sum(abs(u[i] - v[i]) for u, v in zip(pa, pb) for i in range(3))
                 / (len(pa) * 3), 3)


def main() -> None:
    checks: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    # 1 prompt 自洽：口径必须与 check_prompt.py 一致（对 strip() 后的文本算 sha）
    cp = json.loads((HERE / "check_prompt.json").read_text(encoding="utf-8"))
    stripped = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()
    check("prompt_ok_and_sha_self_consistent",
          cp["verdict"] == "PROMPT_OK"
          and cp["sha256"] == hashlib.sha256(stripped.encode()).hexdigest()
          and cp["length"] == len(stripped),
          f"len={cp['length']} sha={cp['sha256'][:12]}")
    check("prompt_forbids_ip_and_weapon_terms",
          not cp["forbidden_hits"] and not cp["missing_constraints"],
          f"hits={cp['forbidden_hits']} missing={cp['missing_constraints']}")

    # 2 配额阻塞被如实记录，且没有伪造产物
    gen = json.loads((HERE / "gen_stdout.json").read_text(encoding="utf-8"))
    blockers = [HERE / f for f in ("probe_run.log", "配额阻塞记录.txt")]
    has_429 = gen.get("http_status") == 429 and "daily submit limit" in gen.get("message", "")
    artifacts = sorted(str(p.name) for p in HERE.glob("artifact_*"))
    check("quota_429_recorded_no_fake_artifacts",
          has_429 and not artifacts and all(p.is_file() for p in blockers),
          f"http={gen.get('http_status')} artifacts={artifacts}")
    check("no_recoverable_job_was_created",
          not (HERE / "probe_report.json").exists()
          and not list(HERE.glob("generated_model_*_viewer.html")),
          "提交阶段即被拒，无 job_id 可 resume")

    # 3 两张概念图在盘上、尺寸对、非空白
    ok1, s1 = nonblank(C1, (1024, 1536))
    ok2, s2 = nonblank(C2, (1024, 1536))
    check("two_concept_images_valid", ok1 and ok2, f"c1={s1} c2={s2}")

    # 4 第二张是同一构图的重绘（负结果：视角没换），不是空白 / 另一个角色
    # 判据订正：初版用像素差异 <30000 判「同一角色」，实测 43317 红。
    # 根因是图生图必然重绘金属划痕等高频纹理，像素差异不能证明构图一致；
    # 改成 16x16 低频 MAE，只看剪影与明暗布局。
    mae = lowfreq_mae(C1, C2)
    check("second_image_shares_composition_not_blank", mae < 30,
          f"lowfreq_mae={mae} (<30 同构图；负结果：视角未换)")

    # 5 对照板有效
    okb, sb = nonblank(BOARD, (1440, 1160))
    check("concept_board_valid", okb, sb)
    stats = json.loads((CONCEPT / "concept_compare_stats.json").read_text(encoding="utf-8"))
    with Image.open(PLAYER) as f:
        pbb = list(f.convert("RGBA").getchannel("A").point(
            lambda v: 255 if v > 8 else 0).getbbox())
    check("board_bboxes_are_measured_not_guessed",
          stats["player_bbox_in_source"] == pbb
          and stats["body_height_px"] == 700
          and stats["foot_y"] == 870,
          f"player_bbox={pbb} foe_bbox={stats['foe_luminance_bbox_in_source']}")

    # 6 对手怪确实不是把玩家旧图换了个名字
    check("foe_concept_is_not_player_v4b", diff(C1, PLAYER) > 20000,
          f"scaled_diff_px={diff(C1, PLAYER)}")

    # 7 游戏源码零改动
    marker = (HERE / "verify_concept.py").stat().st_mtime
    newer = [str(p.relative_to(GAME)) for p in GAME.rglob("*")
             if p.is_file() and ".godot" not in p.parts and p.stat().st_mtime > marker]
    check("game_sources_not_modified", not newer, f"newer={newer[:8]}")

    passed = sum(1 for _, o, _ in checks if o)
    verdict = "CONCEPT_V1_VERIFIED" if passed == len(checks) else "CONCEPT_V1_CHECK_FAILED"
    text = "\n".join(f"{'PASS' if o else 'FAIL'}  {n}  {d}" for n, o, d in checks)
    text += f"\n\n{passed}/{len(checks)} PASS  {verdict}\n"
    (HERE / "verify_concept.log").write_text(text, encoding="utf-8")
    (HERE / "verify_concept_result.json").write_text(
        json.dumps({"verdict": verdict, "passed": passed, "total": len(checks),
                    "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(text)
    raise SystemExit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
