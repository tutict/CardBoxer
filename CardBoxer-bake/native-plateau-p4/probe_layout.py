"""P4 · 落地前的只读结构探针：确认「只改两份 3D 表」是否可行。

回答四件事：
  1. motion_input*.json 的 cards[card].track 是否就是 11 关节表；
  2. hybrid_tracks.json 的卡名与 3D 表卡名是否一一对应；
  3. 三份表当前的 11 关节是否逐值相同（P4 诊断结论复核）；
  4. 两份 3D 表的字节级序列化形态，决定 apply 用文本重排还是数值替换。

纯读盘 + 纯计算，不改任何文件。
用法：python probe_layout.py
产出：data/layout_probe.json
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = HERE.parent.parent / "CardBoxer"
MI = GAME / "data" / "motion_input.json"
MIF = GAME / "data" / "motion_input_foe.json"
CM = GAME / "data" / "card_motion.json"
HYB = HERE / "data" / "hybrid_tracks.json"
OUT = HERE / "data" / "layout_probe.json"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def tracks_of(d: dict) -> dict:
    out = {k: v["track"] for k, v in d["cards"].items()}
    out.update({k: v["track"] for k, v in d.get("motions", {}).items()})
    return out


def joints_of(frame: dict, keys: list[str]) -> dict:
    return {k: tuple(float(x) for x in frame[k]) for k in keys}


def main() -> int:
    mi, mif, cm = load(MI), load(MIF), load(CM)
    hyb = load(HYB)
    keys = list(mi["joint_names"])

    mi_tracks = tracks_of(mi)
    cm_tracks = tracks_of(cm)
    mif_tracks = tracks_of(mif)

    # 三份表 11 关节逐值对账
    def compare(a: dict, b: dict) -> dict:
        bad = []
        if set(a) != set(b):
            return {"same_keys": False,
                    "a_only": sorted(set(a) - set(b)),
                    "b_only": sorted(set(b) - set(a))}
        for card in a:
            if len(a[card]) != len(b[card]):
                bad.append(f"{card}:len")
                continue
            for i, (x, y) in enumerate(zip(a[card], b[card])):
                jx, jy = joints_of(x, keys), joints_of(y, keys)
                if jx != jy:
                    bad.append(f"{card}[{i}]")
        return {"same_keys": True, "mismatches": len(bad),
                "first": bad[:5]}

    cmp_mi_cm = compare(mi_tracks, cm_tracks)
    cmp_mi_mif = compare(mi_tracks, mif_tracks)

    hyb_keys = set(hyb["tracks"])
    mi_keys = set(mi["cards"]) | set(mi.get("motions", {}))
    card_match = {
        "hybrid_tracks": len(hyb_keys),
        "mi_cards": len(mi_keys),
        "hybrid_only": sorted(hyb_keys - mi_keys),
        "mi_only": sorted(mi_keys - hyb_keys),
        "frame_counts_match": all(
            len(hyb["tracks"][c]) == len(mi_tracks[c])
            for c in hyb_keys & mi_keys),
    }

    # 3D 表顶层结构 / 单卡结构 / 单帧结构
    first_card = next(iter(mi["cards"]))
    shape = {
        "mi_root_keys": sorted(mi.keys()),
        "mif_root_keys": sorted(mif.keys()),
        "cm_root_keys": sorted(cm.keys()),
        "mi_first_card": first_card,
        "mi_first_card_keys": sorted(mi["cards"][first_card].keys()),
        "mi_first_frame_keys": sorted(mi["cards"][first_card]["track"][0]),
        "cm_first_frame_keys": sorted(
            cm["cards"][next(iter(cm["cards"]))]["track"][0]),
        "joint_names": keys,
    }

    # 序列化形态
    def shape_of(p: Path) -> dict:
        raw = p.read_bytes()
        txt = raw.decode("utf-8")
        return {
            "bytes": len(raw), "crlf": raw.count(b"\r\n"),
            "lf": raw.count(b"\n"), "has_indent": "\n  " in txt[:400],
            "tail": repr(txt[-24:]),
            "head": repr(txt[:160]),
        }

    report = {
        "game": str(GAME),
        "shape": shape,
        "cmp_mi_cm_11joints": cmp_mi_cm,
        "cmp_mi_mif_11joints": cmp_mi_mif,
        "card_match": card_match,
        "hybrid_changed_frame_total": hyb["changed_frame_total"],
        "serialization": {"motion_input.json": shape_of(MI),
                          "motion_input_foe.json": shape_of(MIF),
                          "card_motion.json": shape_of(CM)},
        "checks": {
            "mi_track_is_11_joints": all(
                k in mi["cards"][first_card]["track"][0] for k in keys),
            "three_tables_11joints_identical": (
                cmp_mi_cm.get("mismatches") == 0
                and cmp_mi_mif.get("mismatches") == 0),
            "hybrid_card_keys_match_mi": (
                not card_match["hybrid_only"]
                and not card_match["mi_only"]),
            "hybrid_frame_counts_match": card_match["frame_counts_match"],
            "mi_and_mif_same_schema": (
                shape["mi_root_keys"] == shape["mif_root_keys"]),
        },
    }
    report["failed"] = [k for k, v in report["checks"].items() if not v]
    report["ok"] = all(report["checks"].values())
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for k, v in report["shape"].items():
        print("SHAPE", k, v)
    print("CMP mi/cm", cmp_mi_cm)
    print("CMP mi/mif", cmp_mi_mif)
    print("CARDS", card_match)
    for name, s in report["serialization"].items():
        print("SER", name, "bytes", s["bytes"], "crlf", s["crlf"],
              "lf", s["lf"], "head", s["head"])
    for k, v in report["checks"].items():
        print("CHECK", k, v)
    print("LAYOUT_PROBE_OK" if report["ok"] else "LAYOUT_PROBE_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
