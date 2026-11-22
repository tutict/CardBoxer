"""Compare fighter.gd's hand-authored poses against the Blender bake, same yardstick.

Both sides are reduced to the same thing -- a flat list of frames, each with the
twelve joints -- so the metrics cannot be tuned to flatter either one.

    python boxer_diff.py            # prints the table
    python boxer_diff.py --html out.html
"""

import json
import math
import sys

HERE = r"C:\Users\tutic\AppData\Local\Temp\fa-run"

REST = {
    "hip": (0.0, -92.0), "shoulder": (0.0, -160.0), "head": (2.0, -184.0),
    "f_elbow": (30.0, -140.0), "f_hand": (48.0, -122.0),
    "b_elbow": (-14.0, -138.0), "b_hand": (-2.0, -112.0),
    "f_knee": (20.0, -46.0), "f_foot": (30.0, 0.0),
    "b_knee": (-18.0, -46.0), "b_foot": (-34.0, 0.0),
}
JOINTS = list(REST)
REACH = {  # card_data.gd, the distance at which damage is decided
    "jab": 118, "cross": 124, "uppercut": 112, "sweep": 138, "wave": 470,
    "throw": 98,
}
STRIKE = {"sweep": "f_foot"}  # everything else that strikes uses the lead glove
NAMES = {
    "jab": "刺拳", "cross": "交叉反击", "uppercut": "上勾拳", "sweep": "扫腿",
    "wave": "气功波", "throw": "投技", "rush": "突进", "backstep": "后撤",
    "guard": "格挡", "sidestep": "侧闪", "focus": "蓄势", "recover": "卸力",
}


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def load_after():
    baked = json.load(open(HERE + r"\baked.json", encoding="utf-8"))
    out = {}
    for cid, card in baked["cards"].items():
        frames = [{"phase": f["phase"], "joints": {j: f[j] for j in JOINTS}}
                  for f in card["track"]]
        out[cid] = {"frames": frames, "impact": card["impact"], "k": card["track"]}
    return out


def load_before():
    ref = json.load(open(HERE + r"\ref.json", encoding="utf-8"))
    out = {}
    for cid, card in ref["cards"].items():
        frames = ref["frames"][cid]
        hit_at = max((i for i, f in enumerate(frames) if f["hit"]), default=len(frames) - 1)
        out[cid] = {"frames": [{"phase": f["phase"], "joints": f["joints"]} for f in frames],
                    "impact": hit_at + 1, "k": None}
    return out


def metrics(cid, entry):
    frames = entry["frames"]
    impact = entry["impact"]
    strike = STRIKE.get(cid, "f_hand")
    m = {"id": cid, "frames": len(frames), "impact": impact, "strike": strike}

    m["snap_in"] = round(max(dist(REST[j], frames[0]["joints"][j]) for j in JOINTS), 1)
    m["snap_out"] = round(max(dist(frames[-1]["joints"][j], REST[j]) for j in JOINTS), 1)

    up = [dist(f["joints"]["shoulder"], f["joints"]["f_elbow"]) for f in frames]
    fo = [dist(f["joints"]["f_elbow"], f["joints"]["f_hand"]) for f in frames]
    r_up = dist(REST["shoulder"], REST["f_elbow"])
    r_fo = dist(REST["f_elbow"], REST["f_hand"])
    m["stretch"] = round(max(max(up) / r_up, max(fo) / r_fo), 2)

    at = frames[min(impact, len(frames)) - 1]["joints"]
    m["strike_at_impact"] = round(at[strike][0], 1)
    m["glove_max"] = round(max(f["joints"][strike][0] for f in frames), 1)

    # Straightness of the striking point's path, measured over the part that
    # actually travels: chord from the most retracted frame to the most extended
    # one. Measuring first-to-last frame is meaningless here -- both are the rest
    # pose, so the chord is zero and the bow reads zero for a perfect arc too.
    pts = [tuple(f["joints"][strike]) for f in frames]
    i_lo = min(range(len(pts)), key=lambda i: pts[i][0])
    i_hi = max(range(len(pts)), key=lambda i: pts[i][0])
    if i_lo > i_hi:
        i_lo, i_hi = i_hi, i_lo
    a, b = pts[i_lo], pts[i_hi]
    chord = dist(a, b)
    span = pts[i_lo:i_hi + 1]
    if chord > 1e-6 and len(span) > 2:
        m["bow"] = round(max(
            abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1])) / chord
            for p in span), 1)
        m["bow_span"] = round(chord, 1)
    else:
        m["bow"] = 0.0
        m["bow_span"] = 0.0

    # Rhythm, measured on the whole body rather than the striking joint: the
    # defensive cards barely move a hand, and a hand-only metric would report them
    # as 100% held no matter what the rest of the body does.
    body = [max(dist(f["joints"][j], g["joints"][j]) for j in JOINTS)
            for f, g in zip(frames[1:], frames[:-1])]
    if body:
        held = sum(1 for d in body if d < 0.5)
        m["held_pct"] = round(100.0 * held / len(body))
        m["drawings"] = 1 + (len(body) - held)   # unique poses Blender actually drew
        m["step_max"] = round(max(body), 1)
    return m


def table(before, after):
    print("%-10s %-7s %6s %9s %8s %7s %8s %7s %6s" % (
        "card", "side", "frames", "drawings", "held%", "snap", "snap_out", "stretch",
        "reach"))
    rows = []
    for cid in before:
        a, b = metrics(cid, before[cid]), metrics(cid, after[cid])
        reach = REACH.get(cid)
        print(cid)
        for tag, m in (("  before", a), ("  after ", b)):
            short = ("%d" % (m["strike_at_impact"] - reach)) if reach else "-"
            print("%-10s %-7s %6d %9d %8d %7.1f %8.1f %7.2f %6s" % (
                "", tag, m["frames"], m["drawings"], m["held_pct"],
                m["snap_in"], m["snap_out"], m["stretch"], short))
        rows.append((cid, a, b))
    return rows


# ─── contact sheet ────────────────────────────────────────────────────────────
# Drawn with fighter.gd's own rules (_draw_limb / _draw_glove / _draw_foot /
# _draw_torso / _draw_head), so the picture is what the game would draw.

BEFORE = {"body": "#fa a8 4a", }
BG = "#0b0c16"
PAL = {
    "before": {"main": "#faa84a", "dark": "#854d21", "trim": "#ffe09e"},
    "after": {"main": "#57c9f5", "dark": "#21597f", "trim": "#c7f5ff"},
}


def mix(hex_color, other, t):
    a = [int(hex_color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def limb(p, q, color, width):
    o = mix(color, "#000000", 0.55)
    return ('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f" '
            'stroke-linecap="round"/><line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
            'stroke="%s" stroke-width="%.1f" stroke-linecap="round"/>'
            '<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="none"/>' % (
                p[0], p[1], q[0], q[1], o, width + 5,
                p[0], p[1], q[0], q[1], color, width,
                q[0], q[1], width * 0.5, color))


def glove(at, base, trim):
    return ('<circle cx="%.1f" cy="%.1f" r="11" fill="%s"/><circle cx="%.1f" cy="%.1f" r="9" '
            'fill="%s"/><circle cx="%.1f" cy="%.1f" r="6" fill="%s"/>' % (
                at[0], at[1], mix(trim, "#000000", 0.35), at[0], at[1], trim,
                at[0], at[1], base))


def foot(at, color):
    return ('<ellipse cx="%.1f" cy="%.1f" rx="18" ry="7.6" fill="%s"/>'
            '<ellipse cx="%.1f" cy="%.1f" rx="16" ry="6.7" fill="%s"/>' % (
                at[0], at[1], mix(color, "#000000", 0.5), at[0], at[1], color))


def figure(p, palette):
    main, dark, trim = palette["main"], palette["dark"], palette["trim"]
    lean = p.get("lean", 0.0)
    out = ['<ellipse cx="0" cy="2" rx="%.1f" ry="%.1f" fill="#000000" opacity="0.35"/>' % (
        46.0, 46.0 * 0.32)]
    out.append(limb(p["shoulder"], p["b_elbow"], mix(dark, "#000000", 0.18), 11))
    out.append(limb(p["b_elbow"], p["b_hand"], mix(dark, "#000000", 0.18), 10))
    out.append(glove(p["b_hand"], mix(dark, "#000000", 0.3), mix(trim, "#000000", 0.3)))
    out.append(limb(p["hip"], p["b_knee"], mix(dark, "#000000", 0.12), 14))
    out.append(limb(p["b_knee"], p["b_foot"], mix(dark, "#000000", 0.12), 12))
    out.append(foot(p["b_foot"], mix(dark, "#000000", 0.2)))
    chest = [p["hip"], p["shoulder"], p["shoulder"], p["hip"]]
    quad = [
        (chest[0][0] - 20, chest[0][1] + 4),
        (chest[1][0] - 26, chest[1][1] + 2),
        (chest[2][0] + 24 + lean, chest[2][1]),
        (chest[3][0] + 20, chest[3][1] + 2),
    ]
    out.append('<polygon points="%s" fill="%s"/>' % (
        " ".join("%.1f,%.1f" % q for q in quad), main))
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#15151f" '
               'stroke-width="6" stroke-linecap="round"/>' % (
                   p["hip"][0] - 20 + lean * 0.4, p["hip"][1] - 2,
                   p["hip"][0] + 20 + lean * 0.4, p["hip"][1] - 2))
    out.append(limb(p["hip"], p["f_knee"], dark, 15))
    out.append(limb(p["f_knee"], p["f_foot"], dark, 13))
    out.append(foot(p["f_foot"], mix(dark, "#000000", 0.05)))
    out.append(limb(p["shoulder"], p["f_elbow"], main, 12))
    out.append(limb(p["f_elbow"], p["f_hand"], main, 11))
    out.append(glove(p["f_hand"], main, trim))
    out.append('<circle cx="%.1f" cy="%.1f" r="20" fill="%s"/>' % (
        p["head"][0], p["head"][1], main))
    out.append('<circle cx="%.1f" cy="%.1f" r="4.2" fill="%s"/>' % (
        p["head"][0] + 9, p["head"][1] - 3, trim))
    return "".join(out)


def sample_frames(entry, count=6):
    n = len(entry["frames"])
    idx = {round(i * (n - 1) / (count - 1)) for i in range(count)}
    idx.add(min(entry["impact"] - 1, n - 1))
    return sorted(idx)


def sheet(before, after, only=None, all_frames=False):
    rows = []
    for cid in before:
        if only and cid not in only:
            continue
        a, b = metrics(cid, before[cid]), metrics(cid, after[cid])
        reach = REACH.get(cid)
        if all_frames:
            idx = list(range(len(before[cid]["frames"])))
            idx_after = list(range(len(after[cid]["frames"])))
        else:
            idx = sample_frames(before[cid])
            idx_after = sample_frames(after[cid])
        cell_w, cell_h, foot_y, origin_x = (168, 200, 175, 80) if all_frames else (250, 235, 205, 85)
        width = cell_w * len(idx) + 130
        parts = []
        for row, (key, entry, idxs) in enumerate((
                ("before", before[cid], idx), ("after", after[cid], idx_after))):
            top = row * (cell_h + 18)
            for col, i in enumerate(idxs):
                if i >= len(entry["frames"]):
                    continue
                frame = entry["frames"][i]
                x = 130 + col * cell_w + origin_x
                y = top + foot_y
                hl = (i + 1) == entry["impact"]
                parts.append('<g transform="translate(%.1f,%.1f)">%s</g>' % (
                    x, y, figure(frame["joints"], PAL[key])))
                if hl:
                    parts.append('<circle cx="%.1f" cy="%.1f" r="86" fill="none" '
                                 'stroke="#ffd166" stroke-width="1.5" stroke-dasharray="4 5" '
                                 'opacity="0.75"/>' % (x, y - 95))
                tag = "命中 %d" % (i + 1) if hl else (frame["phase"][:4])
                parts.append('<text x="%.1f" y="%.1f" fill="%s" font-size="11" '
                             'text-anchor="middle" font-family="ui-monospace,monospace">%s</text>' % (
                                 x, y + 22, "#ffd166" if hl else "#5a6076", tag))
            parts.append('<line x1="130" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#242a44" '
                         'stroke-width="1"/>' % (top + foot_y, width, top + foot_y))
            parts.append('<text x="16" y="%.1f" fill="%s" font-size="12" '
                         'font-family="ui-monospace,monospace">%s</text>' % (
                             top + 40, PAL[key]["main"],
                             "现状 fighter.gd" if key == "before" else "Blender 烘焙"))
        limb = "脚" if b["strike"] == "f_foot" else "拳"
        short = ("　判定 %d，%s到 %d" % (reach, limb, b["strike_at_impact"])) if reach else ""
        rows.append("""
<section>
  <h2>%s <span class="cid">%s</span></h2>
  <div class="stats">帧 <b>%d → %d</b>　画 <b>%d → %d</b>　停帧 <b>%d%% → %d%%</b>　
    首帧跳变 <b>%.1f → %.1f</b> px　挥出倍数 <b>%.2f× → %.2f×</b>　路径弯曲 <b>%.1f → %.1f</b> px%s</div>
  <svg viewBox="0 0 %d %d" width="100%%" preserveAspectRatio="xMidYMid meet">%s</svg>
</section>""" % (
            NAMES.get(cid, cid), cid,
            a["frames"], b["frames"], a["drawings"], b["drawings"],
            a["held_pct"], b["held_pct"],
            a["snap_in"], b["snap_in"],
            a["stretch"], b["stretch"], a["bow"], b["bow"], short,
            width, cell_h * 2 + 18, "".join(parts)))

    html = """<!doctype html><meta charset="utf-8">
<title>牌拳 · 动作对比</title>
<style>
 html,body{margin:0;background:%s;color:#c9cee0;
   font-family:"Helvetica Neue",-apple-system,"Segoe UI",sans-serif}
 header{padding:26px 30px 6px}
 h1{font-size:19px;margin:0 0 6px;color:#eceffb;font-weight:600;letter-spacing:.02em}
 .lede{font-size:13px;color:#7e86a3;max-width:900px;line-height:1.7}
 .lede b{color:#ffd166;font-weight:600}
 section{padding:14px 30px 26px;border-top:1px solid #171c30}
 h2{font-size:14px;margin:10px 0 4px;color:#eceffb;font-weight:600}
 h2 .cid{color:#4d5470;font-family:ui-monospace,monospace;font-size:11px;
   font-weight:400;margin-left:6px}
 .stats{font-size:12px;color:#7e86a3;margin-bottom:4px;line-height:1.6}
 .stats b{color:#c9cee0;font-weight:500}
 svg{display:block}
</style>
<header>
<h1>牌拳 · 动作建模对比</h1>
<div class="lede">每一格都是按 <code>fighter.gd</code> 自己的画法画的（肢体双层描边、拳套三层圆心、
躯干四边形、头圈）。<span style="color:#faa84a">橙</span> = 现行 <code>_build_pose()</code> 手写数值，
<span style="color:#57c9f5">蓝</span> = Blender 骨架烘焙。金色虚线圈是伤害判定的那一帧。
判据：首/末帧相对站姿的跳变、手臂被拉长的倍数、打击点路径偏离直线的距离。</div>
</header>
%s
</body>""" % (BG, "".join(rows))
    return html


def main():
    before, after = load_before(), load_after()
    rows = table(before, after)
    only = None
    if "--only" in sys.argv:
        only = set(sys.argv[sys.argv.index("--only") + 1].split(","))
    if "--html" in sys.argv:
        path = sys.argv[sys.argv.index("--html") + 1]
        open(path, "w", encoding="utf-8").write(
            sheet(before, after, only, all_frames="--allframes" in sys.argv))
        print("\nwrote", path)


main()
