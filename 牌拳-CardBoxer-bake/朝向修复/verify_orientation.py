"""朝向订正判据：源码形态 + 引擎读回 + 改前后像素 A/B，全部只读复算。

不依赖历史归档脚本；G/H/I 路线那些把 ±55 写死的旧断言另行列债。
用法：python verify_orientation.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
LAYER = GAME / "scripts" / "fighter_3d_layer.gd"
ARENA = GAME / "scripts" / "arena.gd"
BACKUP = HERE / "orig" / "pre-orientation" / "fighter_3d_layer.gd"
BEFORE = BAKE / "止损-显示异常" / "shots" / "after-3d" / "display-live.png"
AFTER = HERE / "shots" / "final" / "display-live.png"
ROI = (180, 230, 1100, 520)   # 只取擂台角色区，避开随机手牌


def png_shape(p: Path) -> tuple[int, int]:
    with p.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    import struct
    return struct.unpack(">II", head[16:24])


def changed_pixels(a: Path, b: Path) -> int:
    ia = Image.open(a).convert("RGB").crop(ROI)
    ib = Image.open(b).convert("RGB").crop(ROI)
    diff = ImageChops.difference(ia, ib).tobytes()
    return sum(1 for i in range(0, len(diff), 3)
               if max(diff[i:i + 3]) > 12)


def const_value(src: str, name: str) -> float | None:
    m = re.search(rf"^const {name} := (-?[0-9.]+)[ \t\r]*$",
                  src, re.M)
    return float(m.group(1)) if m else None


def main() -> int:
    layer = LAYER.read_text(encoding="utf-8")
    arena = ARENA.read_text(encoding="utf-8")
    backup = BACKUP.read_text(encoding="utf-8") if BACKUP.is_file() else ""
    final = json.loads((HERE / "data" / "final_shot.json").read_text(
        encoding="utf-8")) if (HERE / "data" / "final_shot.json").is_file() else {}
    scan = json.loads((HERE / "data" / "orientation_probe.json").read_text(
        encoding="utf-8")) if (HERE / "data" / "orientation_probe.json").is_file() else {}
    pay = final.get("payload", {})

    p_yaw = const_value(layer, "DEFAULT_SIDE_YAW")
    f_yaw = const_value(layer, "DEFAULT_FOE_YAW")
    flip_line = re.search(r"^const DEFAULT_SIDE_FLIP := (\w+)[ \t\r]*$",
                          layer, re.M)
    n_shots = len(scan.get("payload", {}).get("shots", []))
    final_pngs = sorted((HERE / "shots" / "final").glob("display-*.png"))
    delta = changed_pixels(BEFORE, AFTER) if BEFORE.is_file() and AFTER.is_file() else 0

    checks = {
        "A_side_yaw_minus55": p_yaw == -55.0,
        "A_foe_yaw_plus55": f_yaw == 55.0,
        "A_flip_false": bool(flip_line) and flip_line.group(1) == "false",
        "A_yaw_signs_opposite_equal_abs": (
            p_yaw is not None and f_yaw is not None
            and p_yaw < 0 < f_yaw and abs(p_yaw) == abs(f_yaw) == 55.0),
        "A_arena_uses_foe_constant": "Fighter3DLayerScript.DEFAULT_FOE_YAW" in arena,
        "A_arena_player_layer_still_default": "Fighter3DLayerScript.new()" in arena,
        "A_old_comment_corrected": "写反" in layer and "-55.0" in layer,
        "B_engine_rc_and_no_errors": (
            final.get("returncode") == 0
            and all(final.get("checks", {}).values())),
        "B_engine_use_3d_and_both_layers": (
            pay.get("use_3d") is True and pay.get("layer_3d") is True
            and pay.get("layer_3d_foe") is True),
        "B_engine_both_overrides": (
            pay.get("player_override") is True
            and pay.get("enemy_override") is True),
        "B_engine_player_yaw_minus55": pay.get("p_yaw") == -55.0,
        "B_engine_foe_yaw_plus55": pay.get("f_yaw") == 55.0,
        "B_engine_both_no_flip": (
            pay.get("p_flip") is False and pay.get("f_flip") is False),
        "C_before_after_pixels_changed": delta > 8000,
        "C_final_pngs_valid": (
            len(final_pngs) == 2
            and all(png_shape(p) == (1280, 720)
                    and p.stat().st_size > 50000 for p in final_pngs)),
        "C_scan_probe_ok": (scan.get("ok") is True and n_shots == 9),
        "C_sv_originals_exist": all(
            (HERE / "shots" / f"o-sv-{r}.png").is_file()
            for r in ("player", "foe")),
        "C_backup_has_old_values": (
            "const DEFAULT_SIDE_YAW := 55.0" in backup
            and "const DEFAULT_FOE_YAW := -55.0" in backup),
    }
    failed = [k for k, v in checks.items() if not v]
    (HERE / "data").mkdir(parents=True, exist_ok=True)
    (HERE / "data" / "verify_orientation.json").write_text(
        json.dumps({"checks": checks, "failed": failed,
                    "changed_pixels": delta, "ok": not failed},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print("CHANGED_PIXELS", delta)
    print(f"PASSED {len(checks) - len(failed)}/{len(checks)}")
    print("FAILED " + ",".join(failed))
    print("ORIENTATION_VERIFIED" if not failed else "ORIENTATION_FAILED")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
