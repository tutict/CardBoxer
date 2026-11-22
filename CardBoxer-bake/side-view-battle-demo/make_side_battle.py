"""《牌拳》KOF 式侧身战斗 GIF：双方侧身相对、水平出拳、地面投影、命中火花与停顿。

复用 battle-demo/battle_script.json 的三回剧本 / 血量怒气轨迹 / 牌型动作伤害绑定，
以及 combat-motion-design/battle_motion_spec.json 的规格断言；角色帧改成本轮
侧身 55° 立绘逐帧图（frames/player、frames/foe）。

与正视版（battle-demo/make_battle.py）的差别：
  * 源帧已水平翻转、角色朝右 = 游戏 +x；合成时玩家不翻、对手翻一次朝左，
    两人真正侧身相对（正视版只是把同一张正面立绘镜像摆两边）。
  * 站位收近到 300px 间距、角色放大到 310px；赢家水平前压出拳。
  * 脚底加软投影并画擂台地面线；命中时星形火花 + 3 帧 hit-stop。
  * 速度线为水平短线且只在两人空隙，不横穿角色。

游戏源码 0 改动；这是离线合成演示，不是实机录屏。

用法： <venv>/python.exe make_side_battle.py
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
FRAMES = {"player": HERE / "frames" / "player",
          "foe": HERE / "frames" / "foe"}
BG = GAME / "background" / "arena.png"
SCRIPT = BAKE / "battle-demo" / "battle_script.json"
SPEC = BAKE / "combat-motion-design" / "battle_motion_spec.json"
TABLE = BAKE / "baked2.json"
FRONT_KEY = BAKE / "battle-demo" / "frames" / "puppet" / "battle-f069.png"
STATS = HERE / "side_battle_stats.json"

W, H = 880, 500
FEET_Y = 384
GROUND_Y = 390
PLAYER_CX, FOE_CX = 320, 560
PLAYER_H, FOE_H = 310, 320
HUD_H, PANEL_TOP = 76, 412

IDLE = (0, 6)
REVEAL = (6, 18)
JUDGE = (18, 21)
ATTACK = (21, 35)
SETTLE = (35, 42)
HIT_FRAME = 27
HITSTOP = (28, 29)          # 与 f27 共用同一帧，制造 3 帧命中停顿

TYPE_CN = {"triple": "三同", "sequence": "三连", "scatter": "散牌"}
CARD_CN = {"jab": "刺拳", "cross": "交叉反击", "wave": "气功波"}
COL_P = (232, 96, 88, 255)
COL_F = (150, 116, 232, 255)
COL_RAGE = (240, 196, 88, 255)
COL_GOLD = (240, 214, 160, 255)


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


_TABLE = None


def card_frames(card: str) -> int:
    global _TABLE
    if _TABLE is None:
        _TABLE = json.loads(TABLE.read_text(encoding="utf-8"))
    return int(_TABLE["cards"][card]["frames"])


def load_rgba(path: Path) -> Image.Image:
    assert path.is_file(), f"missing frame: {path}"
    return Image.open(path).convert("RGBA")


def sprite(card, idx, side):
    return load_rgba(FRAMES[side] / f"{card}_f{idx:03d}.png")


def stance(side):
    return load_rgba(FRAMES[side] / "stance_f000.png")


def shadow_layer(width, height=22):
    im = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse((0, 2, width - 1, height - 3), fill=(6, 8, 16, 128))
    return im.filter(ImageFilter.GaussianBlur(7))


def paste_sprite(base, img, cx, height, flip, dx=0, dy=0,
                 flash=0.0, tilt=0.0):
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


def outlined(d, xy, text, f, fill, stroke=(10, 10, 18, 255), width=2):
    d.text(xy, text, font=f, fill=fill, stroke_width=width, stroke_fill=stroke)


def centered(d, cx, y, text, f, fill, **kw):
    box = d.textbbox((0, 0), text, font=f)
    outlined(d, (cx - (box[2] - box[0]) / 2, y), text, f, fill, **kw)


def bar(d, x, y, w, h, ratio, color, right=False):
    d.rounded_rectangle((x, y, x + w, y + h), radius=4,
                        fill=(38, 42, 58, 235), outline=(96, 104, 128, 255), width=1)
    fw = max(0, int(w * max(0.0, min(1.0, ratio))))
    if fw > 2:
        x0 = x + w - fw if right else x
        d.rounded_rectangle((x0, y, x0 + fw, y + h), radius=4, fill=color)
        d.rectangle((x0 + 2, y + 2, x0 + fw - 2, y + 4), fill=(255, 255, 255, 90))


def draw_card(d, x, y, rank, face_up, accent):
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


def base_canvas(bg):
    im = bg.copy()
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle((0, 0, W, HUD_H), fill=(10, 12, 22, 214))
    d.rectangle((0, PANEL_TOP, W, H), fill=(10, 12, 22, 196))
    d.line((0, HUD_H, W, HUD_H), fill=(120, 106, 160, 120), width=1)
    d.line((0, PANEL_TOP, W, PANEL_TOP), fill=(120, 106, 160, 120), width=1)
    # KOF 式擂台地面线：脚底投影落在这一条上
    d.rectangle((0, GROUND_Y, W, PANEL_TOP), fill=(18, 20, 32, 66))
    d.line((0, GROUND_Y, W, GROUND_Y), fill=(176, 160, 208, 110), width=2)
    return im


def draw_hud(im, turn, hp_p, hp_f, rage_p, rage_f):
    d = ImageDraw.Draw(im, "RGBA")
    d.text((22, 8), "玩家 V4b", font=F_MID, fill=(238, 240, 250, 255))
    d.text((858, 8), "对手怪 V1", font=F_MID, fill=(238, 240, 250, 255), anchor="ra")
    bar(d, 22, 32, 300, 15, hp_p / 100, COL_P)
    bar(d, 558, 32, 300, 15, hp_f / 100, COL_F, right=True)
    bar(d, 22, 53, 300, 7, rage_p / 100, COL_RAGE)
    bar(d, 558, 53, 300, 7, rage_f / 100, COL_RAGE, right=True)
    d.text((330, 30), f"{int(hp_p)}", font=F_SM, fill=(238, 240, 250, 255))
    d.text((550, 30), f"{int(hp_f)}", font=F_SM, fill=(238, 240, 250, 255), anchor="ra")
    centered(d, W / 2, 8, f"第 {turn} 回 / 3", F_MID, COL_GOLD)


def banner(d, text, color=COL_GOLD):
    # V2：横幅收进 HUD 中部空白（x=330..550, y=50..72）。
    # V1 放在 y=390..410 压住脚底/地面线/投影；放到角色区上方又会压住头顶，
    # 因为角色高度 310、脚在 y=384，头顶正好在 y=74。HUD 中间这块是唯一
    # 既不遮角色也不遮出牌区的位置。
    d.rounded_rectangle((308, 50, 572, 72), radius=5,
                        fill=(14, 16, 28, 196), outline=(132, 116, 176, 190), width=1)
    centered(d, W / 2, 54, text, F_SM, color)


def draw_table(im, rnd, f, phase):
    d = ImageDraw.Draw(im, "RGBA")
    face_up = f >= REVEAL[0]
    pcs, fcs = rnd["player_cards"], rnd["foe_cards"]
    d.text((214, 416), "玩家出牌", font=F_SM, fill=(176, 186, 206, 255))
    d.text((666, 416), "对手出牌", font=F_SM, fill=(176, 186, 206, 255), anchor="ra")
    for i, v in enumerate(pcs):
        draw_card(d, 214 + i * 44, 436, v, face_up, (208, 96, 88, 255))
    for i, v in enumerate(fcs):
        draw_card(d, 534 + i * 44, 436, v, face_up, (150, 116, 232, 255))
    centered(d, W / 2, 452, "VS", F_MID, (210, 200, 230, 255))
    pt, ft = TYPE_CN[rnd["player_type"]], TYPE_CN[rnd["foe_type"]]
    if phase in ("reveal", "judge"):
        txt = f"{pt}  VS  {ft}"
        if phase == "judge":
            who = "玩家胜出" if rnd["winner"] == "player" else "对手胜出"
            txt += f"  ▶ {who}"
        banner(d, txt, (150, 226, 246, 255) if phase == "judge" else COL_GOLD)
    elif phase in ("attack", "settle"):
        wt = pt if rnd["winner"] == "player" else ft
        banner(d, f"{wt} · {CARD_CN[rnd['attack']]} ·  {rnd['damage']} 伤害")


def draw_spark(base, cx, cy, t):
    """命中火花：白色核心 + 放射星芒 + 扩散环，比正视版的圆环更「啪」。"""
    d = ImageDraw.Draw(base, "RGBA")
    a = int(250 * max(0.0, 1 - t * 1.25))
    if a <= 0:
        return
    r = 14 + 30 * t
    # V1 画了一圈大椭圆环，缩到战斗画布后像靶心 UI；V2 只留核心 + 星芒。
    d.ellipse((cx - 11, cy - 11, cx + 11, cy + 11), fill=(255, 252, 232, a))
    for k in range(12):
        ang = 2 * math.pi * k / 12 + 0.22
        r0, r1 = r * 0.42, r + 18 * (1 - t)
        d.line((cx + r0 * math.cos(ang), cy + r0 * math.sin(ang),
                cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)),
               fill=(255, 222, 148, a), width=3 if k % 3 == 0 else 2)


def draw_speed_lines(im, winner, t):
    d = ImageDraw.Draw(im, "RGBA")
    if t > 0.42:
        return
    a = int(84 * max(0.0, 1 - t * 2.0))
    if a <= 0:
        return
    direction = 1 if winner == "player" else -1
    x0 = 404 if winner == "player" else 470
    for k in range(4):
        y = 216 + k * 30
        length = 16 + 18 * math.sin(math.pi * min(1.0, t * 2.0 + k * 0.08))
        d.line((x0, y, x0 + direction * length, y - 2 * direction),
               fill=(255, 236, 200, a), width=1)


def render_turn(bg, rnd, f, hp_before, hp_after, rage_before, rage_after,
                stop=False):
    im = base_canvas(bg)
    phase = ("idle" if f < IDLE[1] else
             "reveal" if f < REVEAL[1] else
             "judge" if f < JUDGE[1] else
             "attack" if f < ATTACK[1] else "settle")
    winner = rnd["winner"]
    loser = "foe" if winner == "player" else "player"
    card, n = rnd["attack"], rnd["damage"]
    frames_in_card = card_frames(card)

    if phase == "settle":
        t = min(1.0, (f - SETTLE[0]) / (SETTLE[1] - SETTLE[0]))
        hp_p = hp_before["player"] + (hp_after["player"] - hp_before["player"]) * t
        hp_f = hp_before["foe"] + (hp_after["foe"] - hp_before["foe"]) * t
        rage_p = rage_before["rage_player"] + \
            (rage_after["rage_player"] - rage_before["rage_player"]) * t
        rage_f = rage_before["rage_foe"] + \
            (rage_after["rage_foe"] - rage_before["rage_foe"]) * t
    else:
        hp_p, hp_f = hp_before["player"], hp_before["foe"]
        rage_p, rage_f = rage_before["rage_player"], rage_before["rage_foe"]
    draw_hud(im, rnd["n"], hp_p, hp_f, rage_p, rage_f)

    # 双方脚底投影：先画地面阴影，再画角色（输家在后、赢家在前）
    offsets = {}
    for side in ("player", "foe"):
        cx = PLAYER_CX if side == "player" else FOE_CX
        dx = 0
        if phase == "attack":
            t = (f - ATTACK[0]) / (ATTACK[1] - ATTACK[0])
            if side == winner:
                # 三角脉冲而不是整段正弦：只在命中瞬间贴近，出击前后拉开，
                # 否则 21..35 整段两人都叠在一起，看不出「打了一下」。
                pulse = max(0.0, 1.0 - abs(t - 0.45) / 0.30)
                dx = int(110 * pulse) * (1 if side == "player" else -1)
            else:
                dx = int(40 * max(0.0, 1 - t * 1.7)) * \
                    (1 if side == "foe" else -1)
        offsets[side] = dx
        sh = shadow_layer(146 if side == "player" else 162)
        im.alpha_composite(sh, (int(cx - sh.width / 2 + dx), GROUND_Y - 8))

    for side in (loser, winner):
        cx = PLAYER_CX if side == "player" else FOE_CX
        height = PLAYER_H if side == "player" else FOE_H
        # 源帧角色朝右：玩家不翻；对手翻一次朝左，两人真正侧身相对
        flip = side == "foe"
        dx, dy, flash, tilt = offsets[side], 0, 0.0, 0.0
        img = stance(side)
        if phase == "attack":
            t = (f - ATTACK[0]) / (ATTACK[1] - ATTACK[0])
            if side == winner:
                idx = min(frames_in_card - 1, int(t * frames_in_card))
                img = sprite(card, idx, side)
            else:
                dx = offsets[side] + int(3 * math.sin(f * 2.7))
                dy = int(3 * math.sin(f * 4.1))
                tilt = (9 if side == "foe" else -9) * max(0.0, 1 - t * 1.4)
                flash = 0.8 if f < ATTACK[0] + 3 else 0.2 * max(0.0, 1 - t)
        paste_sprite(im, img, cx, height, flip, dx, dy, flash, tilt)

    if phase == "attack":
        t = (f - ATTACK[0]) / (ATTACK[1] - ATTACK[0])
        draw_speed_lines(im, winner, t)
        lc = FOE_CX if loser == "foe" else PLAYER_CX
        hx = lc + offsets[loser]
        if f <= HIT_FRAME + 3:
            draw_spark(im, hx, FEET_Y - 200, min(1.0, t / 0.55))
        if f in (HIT_FRAME, HIT_FRAME + 1):
            layer = Image.new("RGBA", im.size, (255, 255, 255, 0))
            ImageDraw.Draw(layer).rectangle(
                (0, HUD_H, W, PANEL_TOP), fill=(255, 248, 230, 52))
            im = Image.alpha_composite(im, layer)
        d = ImageDraw.Draw(im, "RGBA")
        centered(d, lc, 100 - int(24 * t), f"-{n}", F_BIG, (255, 168, 96, 255),
                 width=3)
        if stop:
            # 停顿帧与命中帧共用同一渲染参数（f=27），只有这个标签不同；
            # 这就是「3 帧 hit-stop」在画面上唯一可见的差别。
            centered(d, W / 2, 116, "HIT!", F_MID, (255, 226, 168, 255), width=3)

    draw_table(im, rnd, f, phase)
    if phase == "idle":
        banner(ImageDraw.Draw(im, "RGBA"), "同时亮牌准备", (190, 198, 216, 255))
    return im.convert("RGB")


def render_outro(bg, script):
    im = base_canvas(bg)
    out = script["outcome"]
    draw_hud(im, 3, out["player_hp"], out["foe_hp"], 34, 68)
    for side, cx, height, flip in (("player", PLAYER_CX, PLAYER_H, False),
                                   ("foe", FOE_CX, FOE_H, True)):
        sh = shadow_layer(150)
        im.alpha_composite(sh, (int(cx - sh.width / 2), GROUND_Y - 8))
        paste_sprite(im, stance(side), cx, height, flip)
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


def save_gif(frames, path, frame_ms):
    pal = frames[0].convert("P", palette=Image.ADAPTIVE, colors=256)
    q = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    # GIF 延迟单位是 10ms；83ms 会被量化丢总时长（正视版实测）。
    q[0].save(path, save_all=True, append_images=q[1:],
              duration=frame_ms, loop=0, optimize=False, disposal=1)
    with Image.open(path) as g:
        n = g.n_frames
        total = 0
        for i in range(n):
            g.seek(i)
            total += g.info.get("duration", frame_ms)
    out = {"file": path.name, "bytes": path.stat().st_size,
           "src_frames": len(frames), "encoded_frames": n,
           "duration_sum_ms": total,
           "expected_duration_ms": len(frames) * frame_ms,
           "sha256": sha(path)}
    assert out["duration_sum_ms"] == out["expected_duration_ms"], out
    return out


def make_board(frames, script, turn_frames):
    CW, CH = 400, 227
    keys = [("亮牌", 12), ("判定", 19), ("命中", 27), ("停顿", 29), ("结算", 39)]
    board = Image.new("RGB", (20 + len(keys) * (CW + 16),
                              96 + 3 * (CH + 34) + 20), (22, 25, 36))
    d = ImageDraw.Draw(board)
    d.text((20, 12), "《牌拳》KOF 式侧身战斗 · 离线表演关键帧",
           font=F_TITLE, fill=(238, 242, 252))
    d.text((20, 44), "双方侧身相对 · 水平前压出拳 · 地面投影 · 命中火花与 3 帧停顿",
           font=F_SM, fill=(160, 170, 190))
    for ri, rnd in enumerate(script["rounds"]):
        top = 82 + ri * (CH + 34)
        d.text((20, top - 22), f"第 {rnd['n']} 回 · "
               f"{TYPE_CN[rnd['player_type']]} VS {TYPE_CN[rnd['foe_type']]} · "
               f"{'玩家' if rnd['winner'] == 'player' else '对手'}胜 · "
               f"-{rnd['damage']}", font=F_MID, fill=COL_GOLD)
        for ci, (label, lf) in enumerate(keys):
            gf = ri * turn_frames + lf
            x = 20 + ci * (CW + 16)
            board.paste(frames[gf].resize((CW, CH), Image.LANCZOS), (x, top))
            d.text((x + 6, top + CH + 4), f"f{gf:03d} {label}", font=F_SM,
                   fill=(196, 206, 224))
    board.save(HERE / "side-view-combat-keyframe-board.png")

    # 侧身 vs 正视：同一第 2 回命中帧（gf=69）并排，正视图从已归档关键帧读
    assert FRONT_KEY.is_file(), FRONT_KEY
    front = Image.open(FRONT_KEY).convert("RGB")
    side = frames[1 * turn_frames + HIT_FRAME]
    cw, ch = 440, 250
    comp = Image.new("RGB", (cw * 2 + 45, ch + 92), (22, 25, 36))
    dc = ImageDraw.Draw(comp)
    dc.text((15, 12), "同一命中帧 · 正视立绘版 vs KOF 式侧身版（第 2 回 气功波）",
            font=F_TITLE, fill=(238, 242, 252))
    dc.text((15, 42), "左：正面立绘镜像摆两边 / 右：55° 侧视翻转后两人真正相对",
            font=F_SM, fill=(160, 170, 190))
    for i, (im, label) in enumerate(((front, "正视立绘版（战斗演示）"),
                                     (side, "KOF 式侧身版（本轮）"))):
        x = 15 + i * (cw + 15)
        comp.paste(im.resize((cw, ch), Image.LANCZOS), (x, 68))
        dc.text((x + 8, ch + 70), label, font=F_MID, fill=COL_GOLD)
    comp.save(HERE / "side-vs-front-comparison.png")


def main() -> int:
    script = json.loads(SCRIPT.read_text(encoding="utf-8"))
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    assert script["fps"] == 12.5 and script["frame_ms"] == 80
    frame_ms = script["frame_ms"]
    turn_frames = script["turn_frames"]
    assert tuple(script["canvas"]) == (W, H)

    bg = Image.open(BG).convert("RGB").resize((W, H), Image.LANCZOS)
    bg = ImageEnhance.Brightness(bg).enhance(0.70).convert("RGBA")

    # 剧本与规格一致性（与正视版同一套断言）
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

    frames = []
    for ri, rnd in enumerate(script["rounds"]):
        for lf in range(turn_frames):
            lf_eff = HIT_FRAME if lf in HITSTOP else lf
            frames.append(render_turn(bg, rnd, lf_eff, track[ri], track[ri + 1],
                                      track[ri], track[ri + 1],
                                      stop=lf in HITSTOP))
    for _of in range(script["outro_frames"]):
        frames.append(render_outro(bg, script))
    assert len(frames) == 3 * turn_frames + script["outro_frames"]

    outdir = HERE / "frames" / "battle"
    outdir.mkdir(parents=True, exist_ok=True)
    key_indices = [ri * turn_frames + lf for ri in range(3)
                   for lf in (12, 19, 27, 29, 39)]
    for gi in key_indices:
        frames[gi].save(outdir / f"side-battle-f{gi:03d}.png")

    gif = save_gif(frames, HERE / "side-view-combat-KOF-style.gif", frame_ms)
    make_board(frames, script, turn_frames)

    stats = {
        "canvas": [W, H], "fps": script["fps"], "frame_ms": frame_ms,
        "turn_frames": turn_frames, "outro_frames": script["outro_frames"],
        "total_frames": len(frames),
        "segments": {"idle": list(IDLE), "reveal": list(REVEAL),
                     "judge": list(JUDGE), "attack": list(ATTACK),
                     "settle": list(SETTLE)},
        "hit_frame": HIT_FRAME, "hitstop_frames": list(HITSTOP),
        "hitstop_label": "HIT!",
        "push_curve": "triangular pulse: 110 * max(0, 1 - abs(t-0.45)/0.30)",
        "facing": {"player": "right (+x)", "foe": "left (-x)",
                   "rule": "flip = side == 'foe'; source frames already flipped"},
        "layout": {"player_cx": PLAYER_CX, "foe_cx": FOE_CX,
                   "player_h": PLAYER_H, "foe_h": FOE_H,
                   "feet_y": FEET_Y, "ground_y": GROUND_Y,
                   "winner_push_px": 110, "loser_knock_px": 40,
                   "loser_tilt_deg": 9},
        "rounds": script["rounds"], "hp_track": track,
        "outcome": script["outcome"], "gif": gif,
        "key_indices": key_indices,
        "sources": {
            "player_frames": "side-view-battle-demo/frames/player",
            "foe_frames": "side-view-battle-demo/frames/foe",
            "background": "CardBoxer/background/arena.png",
            "front_keyframe": "battle-demo/frames/puppet/battle-f069.png",
            "spec_sha256": sha(SPEC), "table_sha256": sha(TABLE),
            "script_sha256": sha(SCRIPT),
            "side_joints_sha256": sha(HERE / "side_joints.json"),
            "side_stance_sha256": sha(HERE / "side_stance.json"),
            "side_action_sha256": sha(HERE / "side_action.json"),
            "front_key_sha256": sha(FRONT_KEY),
        },
        "not_claimed": script["_not_claimed"],
    }
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"GIF src={gif['src_frames']} enc={gif['encoded_frames']} "
          f"duration={gif['duration_sum_ms']}/{gif['expected_duration_ms']}ms "
          f"bytes={gif['bytes']}")
    print("SIDE_BATTLE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
