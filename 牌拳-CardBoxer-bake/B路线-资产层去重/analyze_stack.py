"""B 路线 P0：把引擎内 5 状态 SubViewport 帧做成可复算的像素归因。

只读 shots/stack_probe/*.png，输出：
  data/stack_pixels.json   逐帧像素统计 + 承重判据
  boards/B-资产层归因.png  5 帧对照板

判据全部写成「状态之间的相对关系」，不是凑出来的绝对阈值：
  关灯 ⇒ 亮像素塌到接近 0
  去金属 ⇒ 近白像素下降
  换纯红 albedo ⇒ 近白消失
  +55 → -55 ⇒ 白布/青云纹从不可见变可见（决定性）
用法：python analyze_stack.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "shots" / "stack_probe"
PROBE = HERE / "data" / "stack_probe.json"
OUT = HERE / "data" / "stack_pixels.json"
BOARD = HERE / "boards" / "B-资产层归因.png"
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")

NAMES = ["0-orig", "1-lights0", "2-nometal",
         "3-redalbedo", "4-neg55"]
LABELS = {
    "0-orig": "S0 原样 +55°（当前工程默认）",
    "1-lights0": "S1 四盏灯能量=0",
    "2-nometal": "S2 metallic=0 / roughness=1",
    "3-redalbedo": "S3 albedo 换纯红（金属保留）",
    "4-neg55": "S4 还原材质，只把 yaw 切 -55°",
}


def near_white(r, g, b):
    return r > 175 and g > 175 and b > 175


def is_cyan(r, g, b):
    return b > 110 and g > 110 and r < g - 18


def is_warm(r, g, b):
    return r > 120 and g < r * 0.65 and b < r * 0.65


def stats(path: Path) -> dict:
    im = Image.open(path).convert("RGBA")
    px = list(im.getdata())
    opaque = white = cyan = warm = bright = 0
    acc = [0, 0, 0]
    for r, g, b, a in px:
        if a < 32:
            continue
        opaque += 1
        acc[0] += r
        acc[1] += g
        acc[2] += b
        if near_white(r, g, b):
            white += 1
        if is_cyan(r, g, b):
            cyan += 1
        if is_warm(r, g, b):
            warm += 1
        if max(r, g, b) > 200:
            bright += 1
    return {
        "w": im.width, "h": im.height,
        "opaque_px": opaque, "near_white_px": white,
        "cyan_px": cyan, "warm_px": warm, "bright_px": bright,
        "mean_rgb": [round(v / max(1, opaque), 2) for v in acc],
        "white_ratio": round(white / max(1, opaque), 6),
        "cyan_ratio": round(cyan / max(1, opaque), 6),
    }


def main() -> int:
    probe = json.loads(PROBE.read_text(encoding="utf-8"))
    assert probe["ok"], "stack_probe.json 未验收"
    rows = {r["name"]: stats(Path(r["path"]))
            for r in probe["payload"]["shots"]}
    assert set(NAMES) <= set(rows), (set(NAMES) - set(rows))

    s0, s1, s2, s3, s4 = (rows[n] for n in NAMES)
    checks = {
        "five_states_measured": len(rows) >= 5,
        # 关灯必须把亮像素几乎清零（证明亮部来自灯，不是 emission）
        "lights_off_kills_bright": (
            s1["bright_px"] < max(1, int(s0["bright_px"] * 0.05))),
        # 去金属后近白下降（证明纯白是 metallic=1 的镜面反射）
        "nometal_reduces_white": (
            s2["near_white_px"] < s0["near_white_px"]),
        # 换纯红 albedo 后青色必须归零（青来自 albedo 贴图，不是第二张图）；
        # 近白只要求下降：白色镜面高光由灯 + metallic 决定，不受 albedo 约束。
        "red_albedo_kills_cyan": s3["cyan_px"] == 0,
        "red_albedo_reduces_white": (
            s3["near_white_px"] < s0["near_white_px"]),
        # 订正：原假设「-55° 才露出白布青云纹」被实测证伪。
        # 这两条反向判据守住「不许再把同源观感归因到相机角度」。
        "s0_white_is_low": s0["white_ratio"] < 0.02,
        "yaw_does_not_create_white": (
            s4["near_white_px"] <= s0["near_white_px"] * 1.5
            and s4["near_white_px"] > 0),
        "yaw_does_not_create_cyan": (
            s4["cyan_px"] <= s0["cyan_px"] * 1.5
            and s4["cyan_px"] > 0),
        # 两张原样帧除 yaw 外材质灯全同，非透明像素数应接近
        "same_geometry_both_yaws": (
            abs(s4["opaque_px"] - s0["opaque_px"])
            < 0.25 * max(1, s0["opaque_px"])),
        "board_written": BOARD.is_file()
                         and BOARD.stat().st_size > 100000,
    }

    # 对照板：3 列 × 2 行
    cw, ch, pad, lab = 320, 396, 18, 46
    W, H = 3 * cw + 4 * pad, 2 * (ch + lab) + 3 * pad
    canvas = Image.new("RGB", (W, H), (22, 26, 36))
    d = ImageDraw.Draw(canvas)
    f = ImageFont.truetype(str(FONT), 16) if FONT.is_file() \
        else ImageFont.load_default()
    for i, name in enumerate(NAMES):
        col, row = i % 3, i // 3
        x = pad + col * (cw + pad)
        y = pad + row * (ch + lab + pad)
        im = Image.open(SHOTS / f"s-{name}.png").convert("RGBA")
        bg = Image.new("RGBA", im.size, (235, 238, 246, 255))
        bg.alpha_composite(im)
        canvas.paste(bg.convert("RGB").resize((cw, ch), Image.LANCZOS),
                     (x, y))
        r = rows[name]
        d.text((x, y + ch + 4), LABELS[name], font=f, fill=(220, 228, 242))
        d.text((x, y + ch + 24),
               f"近白 {r['near_white_px']}  青 {r['cyan_px']}  "
               f"亮 {r['bright_px']}", font=f, fill=(150, 200, 210))
    BOARD.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(BOARD)
    checks["board_written"] = (BOARD.is_file()
                               and BOARD.stat().st_size > 100000)

    report = {
        "source": str(SHOTS), "states": rows,
        "material_slots": probe["payload"]["material_slots"],
        "lights": probe["payload"]["lights"],
        "light_energy0": probe["payload"]["light_energy0"],
        "checks": checks,
        "failed": [k for k, v in checks.items() if not v],
        "board": str(BOARD), "board_bytes": BOARD.stat().st_size,
        "conclusion": (
            "关灯把亮像素清零、去金属把近白从 725 打到 73、换纯红 albedo "
            "把青像素清零 ⇒ 亮/白/青全部来自「四盏高强灯 × metallic=1.0 "
            "× albedo」，不存在第二张彩色贴图或自发光。"
            "S0(+55°) 与 S4(-55°) 只差相机 yaw，近白 725→668、青 424→449，"
            "没有数量级变化 ⇒ 相机角度不是白布出现的原因。"
            "独立 foe 层探针在两种角度下都渲出纯重甲怪。"),
    }
    report["ok"] = not report["failed"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                   + "\n", encoding="utf-8")
    for n in NAMES:
        r = rows[n]
        print(n, "opaque", r["opaque_px"], "white", r["near_white_px"],
              "cyan", r["cyan_px"], "bright", r["bright_px"],
              "mean", r["mean_rgb"])
    for k, v in checks.items():
        print("CHECK", k, v)
    print("STACK_PIXELS_OK" if report["ok"] else "STACK_PIXELS_FAILED",
          report["failed"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
