"""Reference port of CardBoxer's fighter.gd _build_pose(), frame by frame.

Why a port instead of reading the game: the bake has to be compared against what
the game *renders*, including the tick order (_phase_time += delta happens before
the phase test, so a phase's first rendered frame is progress 0 and its progress
never reaches 1.0). Reproducing that here means the comparison numbers are the
engine's numbers, not a re-derivation.

Card timing is parsed out of scripts/card_data.gd so the numbers cannot drift
from the game's own table.

    python boxer_ref.py > ref.json
"""

import json
import re
import sys

GAME = r"D:\Projects\CardBoxer\CardBoxer"
FRAME = 1.0 / 60.0
DELTA = 1.0 / 60.0

# _build_pose() defaults, facing = +1, breathe = 0, no walk bob.
REST = {
    "hip": (0.0, -92.0),
    "shoulder": (0.0, -160.0),
    "head": (2.0, -184.0),
    "f_elbow": (30.0, -140.0),
    "f_hand": (48.0, -122.0),
    "b_elbow": (-14.0, -138.0),
    "b_hand": (-2.0, -112.0),
    "f_knee": (20.0, -46.0),
    "f_foot": (30.0, 0.0),
    "b_knee": (-18.0, -46.0),
    "b_foot": (-34.0, 0.0),
    "lean": 0.0,
}


def parse_cards(path):
    """Pull the CARDS literal out of card_data.gd. Only the fields we need."""
    text = open(path, encoding="utf-8").read()
    body = text.split("const CARDS := {", 1)[1]
    cards = {}
    for m in re.finditer(r'^\t"([a-z]+)": \{$', body, re.M):
        cid = m.group(1)
        chunk = body[m.end():]
        chunk = chunk.split("\n\t},", 1)[0]
        card = {"id": cid}
        for field in ("kind", "cost", "windup", "active", "recover", "damage", "reach"):
            fm = re.search(r'"%s": ([^,\n]+),' % field, chunk)
            if not fm:
                continue
            raw = fm.group(1).strip()
            if raw.startswith('"'):
                card[field] = raw.strip('"')
            elif raw in ("true", "false"):
                card[field] = raw == "true"
            elif raw.startswith("KIND_"):
                card[field] = raw[len("KIND_"):].lower()
            else:
                card[field] = int(raw)
        cards[cid] = card
    return cards


def swing_curve(phase, t):
    if phase == "windup":
        return -0.35 * t
    if phase == "active":
        return 1.0 - (1.0 - t) ** 2
    return max(0.0, 1.0 - t)


def phase_span(card, phase):
    if phase == "windup":
        return float(card.get("windup", 4)) * FRAME
    if phase == "active":
        return max(float(card.get("active", 3)) * FRAME, 0.02)
    return max(float(card.get("recover", 8)) * FRAME, 0.02)


def pose(card, phase, t, sidestep_offset=0.0):
    """fighter.gd _build_pose() for state == ACTION, facing = +1."""
    f = 1.0
    breathe = 0.0
    hip = [0.0, -92.0 + breathe]
    shoulder = [0.0, -160.0 + breathe]
    head = [2.0 * f, -184.0 + breathe]
    lean = 0.0
    f_elbow = [30.0 * f, -140.0 + breathe]
    f_hand = [48.0 * f, -122.0 + breathe]
    b_elbow = [-14.0 * f, -138.0 + breathe]
    b_hand = [-2.0 * f, -112.0 + breathe]
    f_knee = [20.0 * f, -46.0]
    f_foot = [30.0 * f, 0.0]
    b_knee = [-18.0 * f, -46.0]
    b_foot = [-34.0 * f, 0.0]

    cid = card.get("id", "")
    kind = card.get("kind", "")
    sw = swing_curve(phase, t)

    if kind == "guard" and cid == "guard":
        f_elbow = [20.0 * f, -150.0]
        f_hand = [6.0 * f, -176.0]
        b_elbow = [10.0 * f, -142.0]
        b_hand = [24.0 * f, -168.0]
        shoulder[0] += -4.0 * f
        shoulder[1] += 4.0
        lean = -0.15 * f
    elif kind == "guard" and cid == "sidestep":
        hip[0] += -24.0 * f
        hip[1] += -10.0
        shoulder[0] += -30.0 * f
        shoulder[1] += -8.0
        head[0] += -34.0 * f
        head[1] += -8.0
        f_knee[0] += -10.0 * f
        b_hand[0] += -16.0 * f
        b_hand[1] += -18.0
        lean = -0.3 * f
    elif kind == "power" and cid == "focus":
        hip[1] += 10.0 * sw
        shoulder[1] += 6.0 * sw
        f_elbow = [34.0 * f, -120.0]
        f_hand = [46.0 * f, -92.0]
        b_elbow = [-30.0 * f, -120.0]
        b_hand = [-42.0 * f, -92.0]
        lean = 0.0
    elif kind == "power":
        f_hand = [30.0 * f, -150.0]
        b_hand = [-10.0 * f, -140.0]
    elif kind == "move":
        push = 1.0 if cid == "rush" else -1.0
        hip[0] += 16.0 * push * f * sw
        hip[1] += 6.0 * sw
        shoulder[0] += 20.0 * push * f * sw
        shoulder[1] += 2.0 * sw
        head[0] += 24.0 * push * f * sw
        f_knee[0] += 20.0 * push * f * sw
        b_knee[0] -= 10.0 * push * f * sw
        b_foot[0] -= 16.0 * push * f * sw
        lean = 0.3 * push * f * sw
    elif cid == "uppercut":
        lift = sw * 26.0
        f_hand = [34.0 * f, -196.0 + sw * 42.0]
        f_elbow = [22.0 * f, -160.0 + sw * 18.0]
        b_hand = [-8.0 * f, -120.0]
        hip[0] += 6.0 * f * sw
        hip[1] += -lift * 0.4
        shoulder[0] += 10.0 * f * sw
        shoulder[1] += -lift
        head[0] += 12.0 * f * sw
        head[1] += -lift
        f_knee[0] += 4.0 * f
        f_knee[1] += -8.0 * sw
        b_knee[0] += -4.0 * f
        b_knee[1] += -4.0 * sw
        lean = 0.25 * f * sw
    elif cid == "sweep":
        f_knee = [46.0 * f * sw, -34.0]
        f_foot = [96.0 * f * sw, -6.0]
        hip[0] += -8.0 * f
        hip[1] += 18.0 * sw
        shoulder[0] += -14.0 * f
        shoulder[1] += 12.0 * sw
        head[0] += -18.0 * f
        head[1] += 10.0 * sw
        b_hand = [-30.0 * f, -96.0]
        lean = -0.2 * f
    elif cid == "throw":
        f_hand = [66.0 * f * sw, -132.0 - 12.0 * sw]
        f_elbow = [38.0 * f, -146.0]
        b_hand = [52.0 * f * sw, -118.0]
        b_elbow = [24.0 * f, -150.0]
        shoulder[0] += 12.0 * f * sw
        lean = 0.35 * f * sw
    elif cid == "wave":
        f_hand = [62.0 * f, -128.0 - 6.0 * sw]
        f_elbow = [34.0 * f, -140.0]
        b_hand = [48.0 * f, -120.0]
        b_elbow = [22.0 * f, -138.0]
        hip[0] += -10.0 * f * sw
        shoulder[0] += 8.0 * f * sw
        lean = 0.18 * f * sw
    else:
        reach = 82.0 * sw
        f_hand = [(48.0 + reach) * f, -132.0]
        f_elbow = [(30.0 + reach * 0.45) * f, -140.0]
        b_hand = [4.0 * f, -116.0]
        b_elbow = [-8.0 * f, -136.0]
        shoulder[0] += 14.0 * f * sw
        hip[0] += 8.0 * f * sw
        head[0] += 10.0 * f * sw
        lean = 0.22 * f * sw
        f_knee[0] += 6.0 * f * sw

    if sidestep_offset > 0.0:
        hip[0] += sidestep_offset * -f
        shoulder[0] += sidestep_offset * -f
        head[0] += sidestep_offset * -f
        f_elbow[0] += sidestep_offset * -f
        f_hand[0] += sidestep_offset * -f
        b_elbow[0] += sidestep_offset * -f
        b_hand[0] += sidestep_offset * -f
        f_knee[0] += sidestep_offset * -0.4 * f
        b_knee[0] += sidestep_offset * -0.4 * f

    return {
        "hip": hip,
        "shoulder": shoulder,
        "head": head,
        "f_elbow": f_elbow,
        "f_hand": f_hand,
        "b_elbow": b_elbow,
        "b_hand": b_hand,
        "f_knee": f_knee,
        "f_foot": f_foot,
        "b_knee": b_knee,
        "b_foot": b_foot,
        "lean": lean,
    }


def simulate(card):
    """Replay _tick_action() tick by tick; record every frame the engine renders.

    Tick order matters: _phase_time += delta, then the phase test, then render.
    So a phase's first rendered frame has progress 0 and its last rendered frame
    has progress (N-1)/N -- swing never reaches 1.0 inside 'active'.
    """
    frames = []
    phase = "windup"
    phase_time = 0.0
    phase_ticks = 0
    for tick in range(1, 600):
        phase_time += DELTA
        hit_resolved = False
        if phase == "windup":
            if phase_time >= phase_span(card, "windup"):
                phase, phase_time, phase_ticks = "active", 0.0, 0
        elif phase == "active":
            hit_resolved = True  # _resolve_active_hit() runs every active tick
            if phase_time >= phase_span(card, "active") or float(card.get("active", 3)) <= 0.0:
                phase, phase_time, phase_ticks = "recover", 0.0, 0
        elif phase == "recover":
            if phase_time >= phase_span(card, "recover"):
                break

        span = phase_span(card, phase)
        t = min(max(phase_time / span, 0.0), 1.0)
        off = 0.0
        if card["id"] == "sidestep" and phase == "windup":
            off = 0.0
        sw = swing_curve(phase, t) if phase != "" else 0.0
        if card["id"] == "sidestep":
            off = abs(__import__("math").sin(t * 3.141592653589793)) * 66.0
        frames.append({
            "tick": tick,
            "phase": phase,
            "t": round(t, 4),
            "swing": round(sw, 4),
            "joints": pose(card, phase, t, off),
            "hit": hit_resolved,
        })
        phase_ticks += 1
    return frames


def dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def seg(a, b):
    return dist(a, b)


JOINTS = ["hip", "shoulder", "head", "f_elbow", "f_hand", "b_elbow", "b_hand",
          "f_knee", "f_foot", "b_knee", "b_foot"]


def metrics(card, frames):
    out = {"id": card["id"], "kind": card.get("kind"), "reach": card.get("reach", 0)}
    out["frames"] = len(frames)

    first = frames[0]["joints"]
    last = frames[-1]["joints"]
    out["snap_in"] = {j: round(dist(REST[j], first[j]), 1) for j in JOINTS}
    out["snap_out"] = {j: round(dist(last[j], REST[j]), 1) for j in JOINTS}
    out["snap_in_max"] = max(out["snap_in"].values())
    out["snap_out_max"] = max(out["snap_out"].values())

    # Segment lengths across the whole action, as a ratio of the rest pose.
    rest_upper = seg(REST["shoulder"], REST["f_elbow"])
    rest_fore = seg(REST["f_elbow"], REST["f_hand"])
    upper = [seg(f["joints"]["shoulder"], f["joints"]["f_elbow"]) for f in frames]
    fore = [seg(f["joints"]["f_elbow"], f["joints"]["f_hand"]) for f in frames]
    out["upper_ratio"] = [round(min(upper) / rest_upper, 2), round(max(upper) / rest_upper, 2)]
    out["fore_ratio"] = [round(min(fore) / rest_fore, 2), round(max(fore) / rest_fore, 2)]

    # Lead glove: max forward reach and what it is at the tick damage is decided.
    out["glove_max_x"] = round(max(f["joints"]["f_hand"][0] for f in frames), 1)
    hits = [f for f in frames if f["hit"]]
    if hits:
        out["hit_swing"] = [h["swing"] for h in hits]
        out["glove_at_hit"] = round(max(h["joints"]["f_hand"][0] for h in hits), 1)
        out["hit_frames"] = len(hits)

    # Per-frame travel of the lead glove: spikes mean a visible teleport.
    steps = [(frames[i]["joints"]["f_hand"], frames[i - 1]["joints"]["f_hand"])
             for i in range(1, len(frames))]
    mags = [dist(a, b) for a, b in steps]
    if mags:
        ordered = sorted(mags)
        median = ordered[len(ordered) // 2]
        out["glove_step_max"] = round(max(mags), 1)
        out["glove_step_median"] = round(median, 1)
        out["glove_spike_ratio"] = round(max(mags) / median, 2) if median else None
        out["glove_step_max_at"] = frames[mags.index(max(mags)) + 1]["phase"]

    # Straightness of the glove path: max perpendicular distance from the chord.
    pts = [tuple(f["joints"]["f_hand"]) for f in frames]
    a, b = pts[0], pts[-1]
    chord = dist(a, b)
    if chord > 1e-6:
        worst = 0.0
        for p in pts:
            # distance from p to line ab
            num = abs((b[0] - a[0]) * (a[1] - p[1]) - (a[0] - p[0]) * (b[1] - a[1]))
            worst = max(worst, num / chord)
        out["path_bow"] = round(worst, 1)
        out["path_chord"] = round(chord, 1)
    return out


def main():
    cards = parse_cards(GAME + r"\scripts\card_data.gd")
    report = {"rest": REST, "cards": {}, "frames": {}}
    for cid, card in cards.items():
        frames = simulate(card)
        report["frames"][cid] = frames
        report["cards"][cid] = metrics(card, frames)
    json.dump(report, sys.stdout, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
