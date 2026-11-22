"""只读探针：核定 V4b / 对手怪母图的尺寸、RGBA、alpha 包围盒与四角透明。

决定 avatar_foe 到底取 foe-upper.png 还是 foe-front.png；同时把对手怪
剪影体量未达标的既有结论复算一遍，避免口说无凭。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

BAKE = Path(r"D:\Projects\CardBoxer\CardBoxer-bake")
OUT = Path(__file__).resolve().parent
V4B = BAKE / "3d-model-probe-v4b"
FOE = BAKE / "foe-blender-modeling-v1"

V4B_FILES = [
    "v4b-front.png", "v4b-angle25.png", "v4b-angle55.png", "v4b-back35.png",
    "v4b-face-front.png", "v4b-face-25.png", "v4b-upper.png",
]
FOE_FILES = ["foe-front.png", "foe-angle25.png", "foe-angle55.png", "foe-back35.png", "foe-upper.png"]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def probe(path: Path) -> dict:
    with Image.open(path) as src:
        mode = src.mode
        size = list(src.size)
        im = src.convert("RGBA")
    a = im.getchannel("A")
    bbox = list(a.getbbox())
    corners = [im.getpixel((x, y)) for x, y in
               [(0, 0), (size[0] - 1, 0), (0, size[1] - 1), (size[0] - 1, size[1] - 1)]]
    hist = a.histogram()
    return {
        "file": path.name,
        "size": size,
        "mode": mode,
        "sha256": sha256(path),
        "bytes": path.stat().st_size,
        "alpha_bbox": bbox,
        "corner_alpha": [c[3] for c in corners],
        "alpha_0_pct": round(hist[0] / (size[0] * size[1]), 4),
        "alpha_255_pct": round(hist[255] / (size[0] * size[1]), 4),
    }


def main() -> None:
    data = {
        "v4b": [probe(V4B / f) for f in V4B_FILES],
        "foe": [probe(FOE / f) for f in FOE_FILES],
    }
    stats = FOE / "silhouette_stats.json"
    data["silhouette_stats"] = json.loads(stats.read_text(encoding="utf-8")) if stats.is_file() else "MISSING"

    # 与预览阶段的 V4b 源指纹对账
    pm = json.loads((BAKE / "portrait-integration-preview-v4b" / "preview_manifest.json").read_text(encoding="utf-8"))
    src_expect = {**pm["sources"], **pm["face_sources"]}
    live = {r["file"]: r["sha256"] for r in data["v4b"]}
    data["v4b_source_match_preview"] = {
        k: (live.get(k) == v) for k, v in src_expect.items()
    }
    data["v4b_source_all_match"] = all(data["v4b_source_match_preview"].values())

    (OUT / "probe_sources.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for row in data["v4b"] + data["foe"]:
        print(f"{row['file']:24s} {row['size']} {row['mode']:5s} "
              f"bbox={row['alpha_bbox']} corners_a={row['corner_alpha']}")
    print(f"V4B_SOURCE_ALL_MATCH={data['v4b_source_all_match']}")
    print(f"FOE_SILHOUETTE={data['silhouette_stats'] if data['silhouette_stats'] == 'MISSING' else 'see json'}")
    print("PROBE_SOURCES_OK" if data["v4b_source_all_match"] else "PROBE_SOURCES_FAILED")


if __name__ == "__main__":
    main()
