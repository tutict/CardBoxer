"""止损判据：只读复算，不修改工程。

证明四件事：
  ① 可运行工程的 foe-rigged.glb 已回到 I 基线，B round2 不再装载；
  ② 两种启动方式的真实截帧都在盘上且是 1280x720 有效 PNG；
  ③ 默认启动确实是 2D（use_3d=false），带 CARD_BOXER_3D 才是 3D；
  ④ 新启动脚本的形状（3D 开关 + UTF-8 代码页 + 指向存在的 4.5）。
用法：python verify_stopgap.py
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
J = GAME.parent / "CardBoxer-bake" / "route-j-model-rework"
SHA_B_BASELINE = "0edcfe9e455f3c8c9deb7034397c815fd701130ed9a10c2e08800fff789cba88"
SIZE_B_BASELINE = 42914328
SHA_B_ROUND2 = "96d383eec6286efb1099e9fba617c67c8fefa47a4fb5ff69f0c9abb7933831c5"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def png_shape(p: Path) -> tuple[int, int]:
    """不依赖 Pillow：直接读 PNG IHDR。"""
    with p.open("rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return (0, 0)
    return struct.unpack(">II", head[16:24])


def probe(tag: str, name: str) -> dict:
    p = HERE / "shots" / f"{tag}-{name}" / "result.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def main() -> int:
    glb = GAME / "assets" / "3d" / "foe-rigged.glb"
    old_bat = GAME / "play-2d.bat"
    new_bat = GAME / "play.bat"
    hud = GAME / "scripts" / "hud.gd"
    rhythm = GAME / "scripts" / "battle_rhythm.gd"
    rollback = json.loads((J / "data" / "rollback_b.json").read_text(
        encoding="utf-8"))

    old_txt = old_bat.read_text(encoding="utf-8") if old_bat.is_file() else ""
    new_txt = new_bat.read_text(encoding="utf-8") if new_bat.is_file() else ""
    godot_match = re.search(r'set "GODOT=([^"]+)"', new_txt)
    godot_path = Path(godot_match.group(1)) if godot_match else Path("__none__")

    after_pngs = [HERE / "shots" / f"{tag}-{name}" / f"display-{kind}.png"
                  for tag, name in (("after", "default"), ("after", "3d"))
                  for kind in ("live", "frozen")]
    before_pngs = [HERE / "shots" / name / "display-live.png"
                   for name in ("default", "3d")]

    d = probe("after", "default")
    t = probe("after", "3d")
    dp, tp = d.get("payload", {}), t.get("payload", {})

    hit = re.search(r'const HITSTOP_LABEL\s*:=\s*"([^"]*)"',
                    rhythm.read_text(encoding="utf-8")
                    if rhythm.is_file() else "")
    hit_text = hit.group(1) if hit else "中文占位"
    hud_txt = hud.read_text(encoding="utf-8") if hud.is_file() else ""

    checks = {
        "glb_sha_is_i_baseline": sha256(glb) == SHA_B_BASELINE,
        "glb_size_is_i_baseline": glb.stat().st_size == SIZE_B_BASELINE,
        "b_round2_glb_removed": sha256(glb) != SHA_B_ROUND2,
        "rollback_report_all_green": (
            rollback.get("ok") is True
            and all(rollback.get("checks", {}).values())
            and not rollback.get("failed")),
        "default_bat_has_no_3d_switch": (
            "CARD_BOXER_3D" not in old_txt and "--path" in old_txt),
        "new_bat_has_3d_switch": 'set "CARD_BOXER_3D=1"' in new_txt,
        "new_bat_has_utf8_codepage": "chcp 65001" in new_txt,
        "new_bat_godot_exists": godot_path.is_file(),
        "before_evidence_preserved": all(
            p.is_file() and p.stat().st_size > 50000 for p in before_pngs),
        "after_four_pngs_valid": all(
            p.is_file() and p.stat().st_size > 50000
            and png_shape(p) == (1280, 720) for p in after_pngs),
        "default_probe_off": (
            dp.get("use_3d") is False and dp.get("layer_3d") is False
            and dp.get("layer_3d_foe") is False
            and dp.get("player_override") is False
            and dp.get("enemy_override") is False),
        "3d_probe_on": (
            tp.get("use_3d") is True and tp.get("layer_3d") is True
            and tp.get("layer_3d_foe") is True
            and tp.get("player_override") is True
            and tp.get("enemy_override") is True),
        "both_probes_clean": all(
            r.get("returncode") == 0 and r.get("script_errors") == 0
            and r.get("has_opengl") is True and len(r.get("pngs", [])) == 2
            and "error" not in r.get("payload", {})
            for r in (d, t)),
        "hud_uses_systemfont": (
            "SystemFont.new()" in hud_txt and "Microsoft YaHei" in hud_txt),
        "hit_label_is_ascii": bool(hit) and hit_text.isascii(),
    }
    failed = [k for k, v in checks.items() if not v]
    (HERE / "data").mkdir(parents=True, exist_ok=True)
    (HERE / "data" / "verify_stopgap.json").write_text(
        json.dumps({"checks": checks, "failed": failed,
                    "ok": not failed}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for k, v in checks.items():
        print("CHECK", k, v)
    print(f"PASSED {len(checks) - len(failed)}/{len(checks)}")
    print("FAILED " + ",".join(failed))
    print("STOPGAP_VERIFIED" if not failed else "STOPGAP_FAILED")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
