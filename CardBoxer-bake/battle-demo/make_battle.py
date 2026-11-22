"""《牌拳》回合制合战离线表演：一局三回，亮牌 → 比牌型 → 出招/受击 → 结算。

不改游戏源码、不进 Godot。只读既有归档帧：
  玩家 V4b   -> 3d-attack-gifs/frames/puppet_player
  对手怪 V1  -> 3d-attack-gifs/frames/puppet_foe（立绘版）
             或 route-c-real-3d-fix/frames/c-*.png（真3D版，刚修好的连续壳网格）
  背景       -> CardBoxer/background/arena.png

受击是离线表现层（击退 / 闪白 / 抖动 / 冲击环），不是新烘动作帧：
battle_motion_spec.json 里 hit_crush 本就标 new 未烘，hit_light/hit_heavy
虽有 react 轨道，但 puppet 只渲了 jab/cross/wave 三档，两版要能共用同一表现层。

用法： <venv>/python.exe make_battle.py
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
PLAYER = BAKE / "3d-attack-gifs" / "frames" / "puppet_player"
FOE_PUPPET = BAKE / "3d-attack-gifs" / "frames" / "puppet_foe"
FOE_C3D = BAKE / "route-c-real-3d-fix" / "frames"
BG = GAME / "background" / "arena.png"
SPEC = BAKE / "combat-motion-design" / "battle_motion_spec.json"
TABLE = BAKE / "baked2.json"
SCRIPT = HERE / "battle_script.json"
STATS = HERE / "battle_demo_stats.json"

W, H = 880, 500
FEET_Y = 376
PLAYER_CX, FOE_CX = 250, 630
PLAYER_H, FOE_H = 270, 290
HUD_H, PANEL_TOP = 76, 412

IDLE = (0, 6)
REVEAL = (6, 18)
JUDGE = (18, 21)
ATTACK = (21, 35)
SETTLE = (35, 42)

TYPE_CN = {"triple": "三同", "sequence": "三连", "scatter": "散牌"}
CARD_CN = {"jab": "刺拳", "cross": "交叉反击", "wave": "气功波"}
COL_P = (232, 96, 88, 255)
COL_F = (150, 116, 232, 255)
COL_RAGE = (240, 196, 88, 255)
COL_GOLD = (240, 214, 160, 255)
COL_INK = (12, 14, 24)


def font(size, bold=False):
    names = (r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc") if bold \
        else (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf")
    for p in names:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_TITLE = font(21, True)
F_MID = font(16, True)
F_SM = font(13)
F_NUM = font(27, True)
F_BIG = font(40, True)
F_RANK = font(21, True)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rgba(path: Path) -> Image.Image:
    assert path.is_file(), f"missing frame: {path}"
    return Image.open(path).convert("RGBA")


_TABLE_CACHE = None


def card_frames(card: str) -> int:
    global _TABLE_CACHE
    if _TABLE_CACHE is None:
        _TABLE_CACHE = json.loads(TABLE.read_text(encoding="utf-8"))
    return int(_TABLE_CACHE["cards"][card]["frames"])


def sprite(card: str, idx: int, side: str, mode: str) -> Image.Image:
    if side == "player":
        p = PLAYER / f"{card}_f{idx:03d}.png"
    elif mode == "puppet":
        p = FOE_PUPPET / f"{card}_f{idx:03d}.png"
    else:
        p = FOE_C3D / f"c-{card}-f{idx:03d}.png"
    return load_rgba(p)


def stance(side: str, mode: str) -> Image.Image:
    if side == "player":
        p = PLAYER / "jab_f000.png"
    elif mode == "puppet":
        p = FOE_PUPPET / "jab_f000.png"
    else:
        p = FOE_C3D / "c-jab-f000.png"
    return load_rgba(p)


def paste_sprite(base: Image.Image, img: Image.Image, cx: int, height: int,
                 flip: bool, dx: int = 0, dy: int = 0, flash: float = 0.0,
                 tilt: float = 0.0):
    im = img.copy()
    box = im.getchannel("A").getbbox()
    assert box, "empty sprite"
    im = im.crop(box)
    scale = height / im.height
    im = im.resize((max(1, int(im.width * scale)), height), Image.LANCZOS)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if tilt:
        im = im.rotate(tilt, resample=Image.BICUBIC, expand=True)
    if flash > 0:
        a = im.getchannel("A").point(lambda v: int(v * flash))
        white = Image.new("RGBA", im.size, (255, 255, 255, 0))
        white.putalpha(a)
        im = Image.alpha_composite(im, white)
    x = int(cx - im.width / 2 + dx)
    y = int(FEET_Y - im.height + dy)
    base.alpha_composite(im, (x, y))


def outlined(d: ImageDraw.ImageDraw, xy, text, f, fill,
             stroke=(10, 10, 18, 255), width=2):
    d.text(xy, text, font=f, fill=fill, stroke_width=width, stroke_fill=stroke)


def centered(d: ImageDraw.ImageDraw, cx, y, text, f, fill, **kw):
    box = d.textbbox((0, 0), text, font=f)
    outlined(d, (cx - (box[2] - box[0]) / 2, y), text, f, fill, **kw)


def bar(d: ImageDraw.ImageDraw, x, y, w, h, ratio, color, right=False):
    d.rounded_rectangle((x, y, x + w, y + h), radius=4,
                        fill=(38, 42, 58, 235), outline=(96, 104, 128, 255), width=1)
    fw = max(0, int(w * max(0.0, min(1.0, ratio))))
    if fw > 2:
        x0 = x + w - fw if right else x
        d.rounded_rectangle((x0, y, x0 + fw, y + h), radius=4, fill=color)
        d.rectangle((x0 + 2, y + 2, x0 + fw - 2, y + 4), fill=(255, 255, 255, 90))


def draw_card(d: ImageDraw.ImageDraw, x, y, rank, face_up, accent):
    w, h = 38, 54
    if face_up:
        d.rounded_rectangle((x, y, x + w, y + h), radius=5,
                            fill=(238, 240, 246, 255), outline=accent, width=2)
        txt = str(rank)
        bb = d.textbbox((0, 0), txt, font=F_RANK)
        d.text((x + (w - (bb[2] - bb[0])) / 2, y + 13), txt, font=F_RANK,
               fill=(32, 36, 52, 255))
        d.text((x + 4, y + 2), "◆", font=F_SM, fill=accent)
    else:
        d.rounded_rectangle((x, y, x + w, y + h), radius=5,
                            fill=(44, 38, 72, 255), outline=(150, 130, 210, 255), width=2)
        d.polygon([(x + w / 2, y + 12), (x + w - 8, y + h / 2),
                   (x + w / 2, y + h - 12), (x + 8, y + h / 2)],
                  outline=(168, 148, 226, 255))
        d.text((x + 13, y + 20), "牌", font=F_SM, fill=(196, 178, 240, 255))


def draw_impact(base: Image.Image, cx: int, cy: int, t: float):
    d = ImageDraw.Draw(base, "RGBA")
    r = 18 + 46 * t
    a = int(230 * (1 - t))
    d.ellipse((cx - r, cy - r, cx + r, cy + r),
              outline=(255, 226, 168, a), width=max(1, int(5 * (1 - t))))
    for k in range(8):
        ang = 2 * math.pi * k / 8 + t * 0.6
        r0, r1 = r + 6, r + 24 + 12 * t
        d.line((cx + r0 * math.cos(ang), cy + r0 * math.sin(ang),
                cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)),
               fill=(255, 214, 150, a), width=3)


def draw_speed_lines(im: Image.Image, winner: str, t: float):
    """只在两人之间的空隙画短促速度线，不横穿角色身体。

    首版画了 70~116px 的纯白长横线，实测像 UI 分割线一样盖住人物；
    这里收成 4 条 26~48px 的淡短线，且限制在中间空隙 x=392..490。
    """
    d = ImageDraw.Draw(im, "RGBA")
    direction = 1 if winner == "player" else -1
    a = int(96 * max(0.0, 1 - t * 1.6))
    if a <= 0:
        return
    for k in range(4):
        y = 208 + k * 38
        x0 = 404 if winner == "player" else 478
        length = 26 + 22 * math.sin(math.pi * min(1.0, t * 1.4 + k * 0.1))
        d.line((x0, y, x0 + direction * length, y - 3 * direction),
               fill=(255, 236, 200, a), width=1)


def base_canvas(bg: Image.Image) -> Image.Image:
    im = bg.copy()
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, W, HUD_H), fill=(10, 12, 22, 214))
    d.rectangle((0, PANEL_TOP, W, H), fill=(10, 12, 22, 196))
    d.line((0, HUD_H, W, HUD_H), fill=(120, 106, 160, 120), width=1)
    d.line((0, PANEL_TOP, W, PANEL_TOP), fill=(120, 106, 160, 120), width=1)
    return im


def draw_hud(im: Image.Image, turn, hp_p, hp_f, rage_p, rage_f):
    d = ImageDraw.Draw(im, "RGBA")
    d.text((22, 8), "玩家 V4b", font=F_MID, fill=(238, 240, 250, 255))
    d.text((858, 8), "对手怪 V1", font=F_MID, fill=(238, 240, 250, 255),
           anchor="ra")
    bar(d, 22, 32, 300, 15, hp_p / 100, COL_P)
    bar(d, 558, 32, 300, 15, hp_f / 100, COL_F, right=True)
    bar(d, 22, 53, 300, 7, rage_p / 100, COL_RAGE)
    bar(d, 558, 53, 300, 7, rage_f / 100, COL_RAGE, right=True)
    d.text((330, 30), f"{int(hp_p)}", font=F_SM, fill=(238, 240, 250, 255))
    d.text((550, 30), f"{int(hp_f)}", font=F_SM, fill=(238, 240, 250, 255),
           anchor="ra")
    centered(d, W / 2, 8, f"第 {turn} 回 / 3", F_MID, COL_GOLD)


def banner(d: ImageDraw.ImageDraw, text, color=COL_GOLD):
    d.rounded_rectangle((236, 378, 644, 408), radius=7,
                        fill=(14, 16, 28, 230), outline=(132, 116, 176, 220),
                        width=1)
    centered(d, W / 2, 383, text, F_MID, color)


def draw_table(im: Image.Image, rnd, f, phase):
    d = ImageDraw.Draw(im, "RGBA")
    face_up = f >= REVEAL[0]
    pcs, fcs = rnd["player_cards"], rnd["foe_cards"]
    d.text((214, 416), "玩家出牌", font=F_SM, fill=(176, 186, 206, 255))
    d.text((666, 416), "对手出牌", font=F_SM, fill=(176, 186, 206, 255),
           anchor="ra")
    for i, v in enumerate(pcs):
        draw_card(d, 214 + i * 44, 436, v, face_up, (208, 96, 88, 255))
    for i, v in enumerate(fcs):
        draw_card(d, 534 + i * 44, 436, v, face_up, (150, 116, 232, 255))
    centered(d, W / 2, 452, "VS", F_MID, (210, 200, 230, 255))

    pt, ft = TYPE_CN[rnd["player_type"]], TYPE_CN[rnd["foe_type"]]
    if phase in ("reveal", "judge"):
        txt = f"{pt}   VS   {ft}"
        if phase == "judge":
            who = "玩家胜出" if rnd["winner"] == "player" else "对手胜出"
            txt += f"    ▶  {who}"
        banner(d, txt, (150, 226, 246, 255) if phase == "judge" else COL_GOLD)
    elif phase in ("attack", "settle"):
        wt = pt if rnd["winner"] == "player" else ft
        banner(d, f"{wt} · {CARD_CN[rnd['attack']]} ·  {rnd['damage']} 伤害")


def render_turn(bg, rnd, f, mode, hp_before, hp_after, rage_before, rage_after):
    im = base_canvas(bg)
    phase = ("idle" if f < IDLE[1] else
             "reveal" if f < REVEAL[1] else
             "judge" if f < JUDGE[1] else
             "attack" if f < ATTACK[1] else "settle")
    winner, loser = rnd["winner"], ("foe" if rnd["winner"] == "player" else "player")
    card, n = rnd["attack"], rnd["damage"]
    frames_in_card = card_frames(card)

    # 结算段血量从旧值插值到新值
    if phase == "settle":
        t = min(1.0, (f - SETTLE[0]) / (SETTLE[1] - SETTLE[0]))
        hp_p = hp_before["player"] + (hp_after["player"] - hp_before["player"]) * t
        hp_f = hp_before["foe"] + (hp_after["foe"] - hp_before["foe"]) * t
        rage_p = hp_before["rage_player"] + \
            (rage_after["rage_player"] - rage_before["rage_player"]) * t
        rage_f = rage_before["rage_foe"] + \
            (rage_after["rage_foe"] - rage_before["rage_foe"]) * t
    else:
        hp_p, hp_f = hp_before["player"], hp_before["foe"]
        rage_p, rage_f = rage_before["rage_player"], rage_before["rage_foe"]
    draw_hud(im, rnd["n"], hp_p, hp_f, rage_p, rage_f)

    # 输家在后、赢家在前；先画输家避免遮挡
    for side in (loser, winner):
        cx, height = (PLAYER_CX, PLAYER_H) if side == "player" else (FOE_CX, FOE_H)
        flip = side == "foe"
        dx = dy = 0
        flash = 0.0
        tilt = 0.0
        img = stance(side, mode)
        if phase == "attack" and side == winner:
            t = (f - ATTACK[0]) / (ATTACK[1] - ATTACK[0])
            idx = min(frames_in_card - 1, int(t * frames_in_card))
            img = sprite(card, idx, side, mode)
            # 前压 120px：站架间距 380px，出拳手才够得着对手
            dx = int(120 * math.sin(math.pi * min(1.0, t * 1.25))) * \
                (1 if side == "player" else -1)
        elif phase == "attack" and side == loser:
            t = (f - ATTACK[0]) / (ATTACK[1] - ATTACK[0])
            knock = int(34 * max(0.0, 1 - t * 1.7))
            dx = knock * (1 if side == "foe" else -1) + int(4 * math.sin(f * 2.7))
            dy = int(4 * math.sin(f * 4.1))
            tilt = (7 if side == "foe" else -7) * max(0.0, 1 - t * 1.4)
            flash = 0.78 if f < ATTACK[0] + 3 else 0.22 * max(0.0, 1 - t)
        paste_sprite(im, img, cx, height, flip, dx, dy, flash, tilt)

    if phase == "attack":
        t = (f - ATTACK[0]) / (ATTACK[1] - ATTACK[0])
        draw_speed_lines(im, winner, t)
        if t < 0.55:
            lc = FOE_CX if loser == "foe" else PLAYER_CX
            draw_impact(im, lc, FEET_Y - 165, min(1.0, t / 0.55))
        if f < ATTACK[0] + 3:
            layer = Image.new("RGBA", im.size, (255, 255, 255, 0))
            ImageDraw.Draw(layer).rectangle(
                (0, HUD_H, W, PANEL_TOP), fill=(255, 248, 230, 46))
            im = Image.alpha_composite(im, layer)
        d = ImageDraw.Draw(im, "RGBA")
        lc = FOE_CX if loser == "foe" else PLAYER_CX
        centered(d, lc, 100 - int(24 * t), f"-{n}", F_BIG, (255, 168, 96, 255),
                 width=3)

    draw_table(im, rnd, f, phase)
    if phase == "idle":
        banner(ImageDraw.Draw(im, "RGBA"), "同时亮牌准备", (190, 198, 216, 255))
    return im.convert("RGB")


def render_outro(bg, script, f, mode):
    im = base_canvas(bg)
    out = script["outcome"]
    draw_hud(im, 3, out["player_hp"], out["foe_hp"], 34, 68)
    paste_sprite(im, stance("player", mode), PLAYER_CX, PLAYER_H, False)
    paste_sprite(im, stance("foe", mode), FOE_CX, FOE_H, True)
    d = ImageDraw.Draw(im, "RGBA")
    d.rounded_rectangle((190, 140, 690, 310), radius=14,
                        fill=(14, 16, 28, 224), outline=COL_GOLD, width=2)
    centered(d, W / 2, 158, "本 局 结 算", F_MID, (190, 198, 216, 255))
    centered(d, W / 2, 188, "玩家 V4b  胜", F_BIG, (150, 226, 246, 255), width=3)
    centered(d, W / 2, 244,
             f"剩余兵力   {out['player_hp']}  :  {out['foe_hp']}",
             F_TITLE, COL_GOLD)
    centered(d, W / 2, 276, out["text"], F_SM, (190, 198, 216, 255))
    return im.convert("RGB")


def save_gif(frames, path: Path):
    pal = frames[0].convert("P", palette=Image.ADAPTIVE, colors=256)
    q = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    # optimize=True 会让 Pillow 丢弃被合并帧的延迟（首版实测 11360 vs 11620ms）。
    # 沿用 C 路线口径：optimize=False + disposal=1，合并帧累加 duration，总时长守恒。
    q[0].save(path, save_all=True, append_images=q[1:],
              duration=FRAME_MS, loop=0, optimize=False, disposal=1)
    with Image.open(path) as g:
        n = g.n_frames
        total = 0
        for i in range(n):
            g.seek(i)
            total += g.info.get("duration", FRAME_MS)
    out = {"file": path.name, "bytes": path.stat().st_size,
           "src_frames": len(frames), "encoded_frames": n,
           "duration_sum_ms": total,
           "expected_duration_ms": len(frames) * FRAME_MS,
           "sha256": sha(path)}
    assert out["duration_sum_ms"] == out["expected_duration_ms"], out
    return out


def make_board(frames_by_mode, script):
    """3 行 × 4 列：每回的 亮牌 / 判定 / 命中 / 结算 四个关键时刻（立绘版）。"""
    CW, CH = 400, 227
    keys = [("亮牌", 12), ("判定", 19), ("命中", 27), ("结算", 39)]
    board = Image.new("RGB", (CW * 4 + 20 * 5, (CH + 34) * 3 + 96), (22, 25, 36))
    d = ImageDraw.Draw(board)
    d.text((20, 12), "《牌拳》三回卡牌对战 · 离线表演关键帧（立绘版）",
           font=F_TITLE, fill=(238, 242, 252))
    d.text((20, 44), "亮牌 → 比牌型 → 赢家出招 / 输家受击 → 扣血攒怒 → 三回结算",
           font=F_SM, fill=(160, 170, 190))
    for ri, rnd in enumerate(script["rounds"]):
        top = 74 + ri * (CH + 34)
        d.text((20, top - 22), f"第 {rnd['n']} 回 · "
               f"{TYPE_CN[rnd['player_type']]} VS {TYPE_CN[rnd['foe_type']]} · "
               f"{'玩家' if rnd['winner'] == 'player' else '对手'}胜 · "
               f"-{rnd['damage']}", font=F_MID, fill=COL_GOLD)
        for ci, (label, lf) in enumerate(keys):
            gf = ri * TURN_FRAMES + lf
            im = frames_by_mode["puppet"][gf].resize((CW, CH), Image.LANCZOS)
            x = 20 + ci * (CW + 20)
            board.paste(im, (x, top))
            d.text((x + 6, top + CH + 4), f"f{gf:03d} {label}", font=F_SM,
                   fill=(196, 206, 224))
    board.save(HERE / "battle-demo-keyframe-board.png")

    # 两版同帧对照：整帧里两套对手怪外观接近，改成「右侧对手区域裁切并排」，
    # 让 puppet 的图像变形与 C 真 3D 网格蒙皮差异真的看得出来。
    gf = 1 * TURN_FRAMES + 27
    # y 收到 376：避开 378..408 的牌型横幅底板，也刚好保住脚底
    crop = (430, 88, 880, 376)
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    comp = Image.new("RGB", (cw * 2 + 45, ch + 92), (22, 25, 36))
    dc = ImageDraw.Draw(comp)
    dc.text((15, 12), "同一命中帧 · 对手怪局部放大对照（第 2 回 气功波）",
            font=F_TITLE, fill=(238, 242, 252))
    dc.text((15, 42), "左：立绘 puppet 图像变形   右：C 路线真 3D 连续壳网格蒙皮",
            font=F_SM, fill=(160, 170, 190))
    for i, (mode, label) in enumerate((("puppet", "立绘版 / 2D puppet"),
                                       ("c3d", "真3D网格版 / C 路线"))):
        x = 15 + i * (cw + 15)
        comp.paste(frames_by_mode[mode][gf].crop(crop), (x, 68))
        dc.text((x + 8, ch + 70), label, font=F_MID, fill=COL_GOLD)
    comp.save(HERE / "battle-demo-two-version-comparison.png")


def main() -> int:
    script = json.loads(SCRIPT.read_text(encoding="utf-8"))
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    # GIF 延迟单位是 10ms；83ms 会被量化成 80/90ms 并丢总时长（首版实测
    # 11360 vs 11620ms）。用 80ms = 12.5fps，所有累加都是 10 的整数倍。
    assert script["fps"] == 12.5 and script["frame_ms"] == 80
    global FRAME_MS, TURN_FRAMES
    FRAME_MS = script["frame_ms"]
    TURN_FRAMES = script["turn_frames"]
    W2, H2 = script["canvas"]
    assert (W2, H2) == (W, H)

    bg = Image.open(BG).convert("RGB").resize((W, H), Image.LANCZOS)
    bg = ImageEnhance.Brightness(bg).enhance(0.74).convert("RGBA")

    # 剧本与规格一致性：伤害档必须来自 spec，不是脚本里随手写的
    for rnd in script["rounds"]:
        wt = rnd["player_type"] if rnd["winner"] == "player" else rnd["foe_type"]
        assert rnd["attack"] == spec["card_type_binding"][wt]["winner_card"]
        assert rnd["damage"] == spec["damage_tiers"][wt]["base"]
    track = script["hp_track"]
    for i, rnd in enumerate(script["rounds"]):
        prev, cur = track[i], track[i + 1]
        if rnd["winner"] == "player":
            assert cur["foe"] == prev["foe"] - rnd["damage"]
        else:
            assert cur["player"] == prev["player"] - rnd["damage"]

    all_frames = {}
    for mode in ("puppet", "c3d"):
        frames = []
        for ri, rnd in enumerate(script["rounds"]):
            for lf in range(TURN_FRAMES):
                frames.append(render_turn(bg, rnd, lf, mode,
                                          track[ri], track[ri + 1],
                                          track[ri], track[ri + 1]))
        for of in range(script["outro_frames"]):
            frames.append(render_outro(bg, script, of, mode))
        all_frames[mode] = frames
        assert len(frames) == 3 * TURN_FRAMES + script["outro_frames"]

    (HERE / "frames").mkdir(exist_ok=True)
    key_indices = [ri * TURN_FRAMES + lf for ri in range(3)
                   for lf in (12, 19, 27, 39)]
    # 关键帧落盘，供看图与判据做非空/来源核对
    for mode, frames in all_frames.items():
        outdir = HERE / "frames" / mode
        outdir.mkdir(parents=True, exist_ok=True)
        for gi in key_indices:
            frames[gi].save(outdir / f"battle-f{gi:03d}.png")

    gifs = {}
    for mode, frames in all_frames.items():
        name = "battle-demo-portrait-version.gif" if mode == "puppet" else "battle-demo-real-3d-version.gif"
        gifs[mode] = save_gif(frames, HERE / name)

    make_board(all_frames, script)

    stats = {
        "canvas": [W, H], "fps": script["fps"],
        "frame_ms": FRAME_MS, "turn_frames": TURN_FRAMES,
        "outro_frames": script["outro_frames"],
        "total_frames": len(all_frames["puppet"]),
        "segments": {"idle": list(IDLE), "reveal": list(REVEAL),
                     "judge": list(JUDGE), "attack": list(ATTACK),
                     "settle": list(SETTLE)},
        "rounds": script["rounds"], "hp_track": track,
        "outcome": script["outcome"],
        "modes": gifs,
        "key_indices": key_indices,
        "sources": {
            "player_frames": str(PLAYER.relative_to(BAKE)).replace("\\", "/"),
            "foe_puppet_frames": str(FOE_PUPPET.relative_to(BAKE)).replace("\\", "/"),
            "foe_c3d_frames": str(FOE_C3D.relative_to(BAKE)).replace("\\", "/"),
            "background": "CardBoxer/background/arena.png",
            "spec_sha256": sha(SPEC), "table_sha256": sha(TABLE),
            "script_sha256": sha(SCRIPT),
        },
        "not_claimed": script["_not_claimed"],
    }
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    for mode, g in gifs.items():
        print(f"GIF {mode}: src={g['src_frames']} enc={g['encoded_frames']} "
              f"duration={g['duration_sum_ms']}/{g['expected_duration_ms']}ms "
              f"bytes={g['bytes']}")
    print("BATTLE_DEMO_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
