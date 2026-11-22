"""Render a planning illustration using the existing captured arena, not a game UI."""
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("2026-11-22-ui-layout.png")
BG = "#0C1018"
SURFACE = "#111720"
INK = "#EEF1F6"
SECONDARY = "#B7C3D2"
MUTED = "#768393"
BORDER = "#364252"
GOLD = "#E8C16E"
COLORS = {"attack": "#CE7B76", "guard": "#88A9C9", "move": "#8DB8A6", "power": "#AB99C7"}
img = Image.new("RGB", (1600, 900), BG)
d = ImageDraw.Draw(img)

@lru_cache(None)
def font(size, bold=False):
    return ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc", size)

def label(text, x, y, size=18, color=INK, bold=False, max_width=None, center=False):
    f = font(size, bold)
    box = f.getbbox(text)
    width = box[2] - box[0]
    height = box[3] - box[1]
    if max_width is not None and width > max_width:
        raise ValueError(f"Text overflow: {text!r}, {width}px > {max_width}px")
    if y < 0 or y+height > 900:
        raise ValueError(f"Vertical text overflow: {text!r}, y={y}, height={height}")
    if center:
        x -= width / 2
    d.text((x - box[0], y - box[1]), text, font=f, fill=color)

def rect(x, y, w, h, fill=SURFACE, outline=None, width=1):
    d.rectangle((round(x), round(y), round(x+w-1), round(y+h-1)), fill=fill, outline=outline, width=width)

def dashed_box(x, y, w, h, color=BORDER):
    for at in range(round(x), round(x+w), 9):
        end = min(at+4, round(x+w-1))
        d.line((at, y, end, y), fill=color)
        d.line((at, y+h-1, end, y+h-1), fill=color)
    for at in range(round(y), round(y+h), 9):
        end = min(at+4, round(y+h-1))
        d.line((x, at, x, end), fill=color)
        d.line((x+w-1, at, x+w-1, end), fill=color)

def button(text, x, y, w, h, primary=False, size=18):
    rect(x, y, w, h, GOLD if primary else "#19212D", GOLD if primary else BORDER)
    label(text, x+w/2, y+(h-18)/2, size, BG if primary else SECONDARY, center=True, max_width=w-12)

def range_cells(x, y, reach, cell=20, size=16):
    for i, word in enumerate(("贴", "中", "远")):
        xx = x+i*(cell+3)
        active = i in reach
        rect(xx, y, cell, 20, "#263646" if active else "#151D27", "#74899F" if active else BORDER)
        label(word, xx+cell/2, y+2, size, INK if active else MUTED, center=True, max_width=cell-2)

# Preserve the source arena and actor proportions. The upper 48px is the newly freed area.
baseline = Image.open(ROOT / "logs/ui-reference-plan-shots/06-ordered-plan.png").convert("RGB").resize((1600, 900), Image.Resampling.LANCZOS)
img.paste(baseline.crop((0, 366, 1600, 656)), (0, 366))
d = ImageDraw.Draw(img)
rect(0, 318, 1600, 48, "#161C28")
label("擂台展示区", 800, 339, 18, MUTED, center=True)

# Compact, stable match header.
rect(0, 0, 1600, 136, "#101620")
for name, x in (("avatar_player.png", 48), ("avatar_foe.png", 1508)):
    portrait = Image.open(ROOT / "CardBoxer/assets/portraits" / name).convert("RGBA").resize((44, 44), Image.Resampling.LANCZOS)
    img.paste(portrait, (x, 26), portrait)
for side, x, name, hp_color in (("p", 48, "你  100", "#C8A86B"), ("e", 940, "青岚  100", "#81A8C1")):
    name_x = 112 if side == "p" else 1036
    label(name, name_x, 15, 21, INK, True)
    rect(name_x, 43, 452, 17, "#263141", BORDER)
    rect(name_x+1, 44, 450, 15, hp_color)
    rect(name_x, 67, 452, 5, "#302A2D")
    label("怒火 0%", name_x, 80, 16, SECONDARY)
    for i, talent in enumerate(("掠影", "趁隙", "追风") if side == "p" else ("抢拍", "压制", "顺势")):
        tx = x+208*i
        rect(tx, 101, 196, 26, SURFACE)
        label(str(i+1), tx+10, 106, 16, MUTED)
        label(talent, tx+31, 104, 18, SECONDARY)
label("第 1 局 · 第 1 轮 / 6", 800, 13, 16, SECONDARY, center=True)
label("0 : 0", 800, 43, 30, INK, True, center=True)
button("暂停 P", 684, 97, 110, 28, size=16)
button("重开 R", 806, 97, 110, 28, size=16)

# Corresponding five-beat plans keep 54px slots and separate their risk labels.
rect(0, 136, 1600, 182, "#101620")
label("你 · 贴身", 48, 153, 18)
label("公开预估", 244, 155, 16, SECONDARY)
pattern = "三连  +2  ×1.15"
label(pattern, 1552-(font(16).getbbox(pattern)[2]), 155, 16, GOLD)
label("青岚 · 3明 2暗", 48, 242, 18)
label("同一列对应同一拍", 1220, 243, 16, SECONDARY)
names = ["侧闪", "刺拳", "后撤", "格挡", "蓄势"]
stats = ["起手2", "起手4 · 4伤", "起手3", "起手2", "起手10"]
kinds = ["guard", "attack", "move", "guard", "power"]
risks = ["可闪避", "可确反", "可完成", "结果未定", "可完成"]
foes = ["上勾拳", None, "格挡", None, "突进"]
foe_stats = ["起手8 · 10伤", "", "起手2", "", "起手4"]
foe_kinds = ["attack", None, "guard", None, "move"]
slot_w = (1504-4*10)/5
for i in range(5):
    x = 48+i*(slot_w+10)
    for enemy, y in ((False, 180), (True, 264)):
        name = foes[i] if enemy else names[i]
        kind = foe_kinds[i] if enemy else kinds[i]
        rect(x, y, slot_w, 54, SURFACE, BORDER)
        label(f"{i+1:02d}", x+10, y+11, 16, SECONDARY)
        if name is None:
            label("?", x+slot_w/2, y+8, 32, SECONDARY, True, center=True)
            continue
        rect(x, y, 2, 54, COLORS[kind])
        label(name, x+42, y+6, 20, INK, True, max_width=slot_w-170 if not enemy else slot_w-60)
        label(foe_stats[i] if enemy else stats[i], x+42, y+33, 16, SECONDARY, max_width=170)
        if (not enemy and i == 1) or (enemy and i == 0):
            range_cells(x+slot_w-72, y+31, [0, 1] if not enemy else [0])
        if not enemy:
            rx = x+slot_w-118
            if i == 3:
                dashed_box(rx, y+5, 110, 22, MUTED)
            else:
                rect(rx, y+5, 110, 22, "#1B2938", "#617B95")
            label("预估·"+risks[i], rx+55, y+8, 16, SECONDARY, center=True, max_width=104)

# An existing public card detail occupies only the left side, away from both fighters.
rect(48, 423, 336, 222, "#101620", BORDER)
label("刺拳", 64, 440, 25, INK, True)
label("起手4 · 4伤 · 贴身–中距", 64, 478, 17, SECONDARY, max_width=304)
label("连段起始 · 1点", 64, 507, 17, SECONDARY)
label("收招6 · 打空8 · 打断2", 64, 535, 17, SECONDARY, max_width=304)
label("预估 17–17伤", 64, 565, 18, GOLD)
label("抢中攻击起手时打康；", 64, 595, 17, SECONDARY)
label("轻打断力无法压过霸体。", 64, 620, 17, SECONDARY, max_width=304)

# Ten-card maximum case, with five selected cards and the same public plan.
rect(0, 656, 1600, 244, "#0E141D")
d.line((48, 656, 1552, 656), fill=BORDER)
label("手牌 10", 48, 671, 20, INK, True)
label("已编排 5 / 5", 191, 673, 18, GOLD)
label("换牌 0 / 3", 1058, 673, 17, SECONDARY)
button("撤回", 1252, 660, 120, 40)
button("开打", 1384, 660, 168, 40, True, size=20)
cards = [
    ("侧闪", 2, "闪", "guard", 2, 0, []),
    ("刺拳", 1, "起", "attack", 4, 4, [0, 1]),
    ("后撤", 8, "移", "move", 3, 0, []),
    ("格挡", 9, "挡", "guard", 2, 0, []),
    ("蓄势", 3, "势", "power", 10, 0, []),
    ("破防击", 4, "终", "attack", 9, 8, [0, 1]),
    ("霸体重拳", 6, "独", "attack", 10, 10, [0, 1]),
    ("追击拳", 7, "连", "attack", 6, 5, [0, 1]),
    ("气功波", 5, "独", "attack", 10, 9, [1, 2]),
    ("佯攻", 1, "骗", "move", 4, 0, [0, 1]),
]
cw = (1504-9*12)/10
for i, (name, rank, role, kind, startup, damage, reach) in enumerate(cards):
    x = 48+i*(cw+12)
    y = 700 if i < 5 else 708
    rect(x, y, cw, 172, "#121922", "#827553" if i < 5 else BORDER)
    rect(x, y, 2, 172, COLORS[kind])
    label(f"{i+1:02d}" if i < 5 else role, x+11, y+14, 17, GOLD if i < 5 else COLORS[kind])
    label(str(rank), x+cw-26, y+11, 24, SECONDARY, True)
    label(name, x+10, y+52, 21, INK, True, max_width=cw-20)
    stat = f"起手{startup}"+(f" · {damage}伤" if damage else "")
    label(stat, x+10, y+93, 17, SECONDARY, max_width=cw-20)
    if reach:
        range_cells(x+10, y+128, reach)
    button("换", x+cw-44, y+141, 34, 24, size=16)

label("1–0 编排 · 拖动换序 · Shift+数字 换牌 · 空格开打", 48, 882, 16, SECONDARY)
label("方案示意 · 非运行截图", 924, 882, 16, MUTED)
label("牌堆26 · 弃牌0", 1390, 882, 16, SECONDARY, max_width=162)
img.save(OUT)
print(f"Rendered planning illustration: {OUT} (1600x900); no text overflow")
