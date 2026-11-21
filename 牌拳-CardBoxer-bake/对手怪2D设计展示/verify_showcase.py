"""对手怪 2D 设计展示的承重判据（离线 + 真实 HTTP + 源图一致性）。

只证明「展示用的就是那两张概念图、页面完全离线、抹水印没碰造型、
排版产物非空且参数可复算」。不证明造型好看，也不证明能进游戏。
"""
from __future__ import annotations

import functools
import hashlib
import http.server
import json
import re
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
SRC = BAKE / "对手怪模型探针V1"
CONCEPT = SRC / "概念图"
HTML = HERE / "对手怪V1-2D设计查看器.html"
STATS = json.loads((HERE / "design_stats.json").read_text(encoding="utf-8"))
LOG = HERE / "verify_showcase.log"
RESULT = HERE / "verify_showcase_result.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def colors(p: Path) -> int:
    with Image.open(p) as f:
        small = f.convert("RGB").resize((120, 120), Image.Resampling.BILINEAR)
    px = list(small.get_flattened_data() if hasattr(small, "get_flattened_data")
              else small.getdata())
    return len(set(px))


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def http_probe(names: list[str]) -> dict:
    handler = functools.partial(Quiet, directory=str(HERE))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    out = {}
    try:
        port = srv.server_address[1]
        for name in names:
            url = f"http://127.0.0.1:{port}/{urllib.parse.quote(name)}"
            with urllib.request.urlopen(url, timeout=5) as r:
                body = r.read()
                out[name] = {"status": r.status, "bytes": len(body),
                             "disk_bytes": (HERE / name).stat().st_size}
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)
    return out


def main() -> None:
    checks: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    html = HTML.read_text(encoding="utf-8")
    forbidden = ["http://", "https://", "cdn.", "fetch(", "__SHOTS__", "__FACTS__", "__CROPS__"]
    hits = [t for t in forbidden if t in html]
    check("html_exists_and_offline", HTML.is_file() and not hits, f"hits={hits}")

    files = re.findall(r'"file":\s*"([^"]+)"', html)
    relative_ok = bool(files) and all(
        ":" not in f and "//" not in f and not f.startswith("/")
        and "/" not in f and (HERE / f).is_file() for f in files)
    check("all_img_src_exist_and_relative", relative_ok, f"n={len(files)} files={files[:3]}")

    probe_names = ["对手怪V1-2D设计查看器.html", "foe-full-original.png",
                   "对手怪V1-2D设计板.png", "玩家V4b-对手怪V1-概念对照.png"]
    http = http_probe(probe_names)
    check("http_200_for_html_and_assets",
          len(http) == len(probe_names)
          and all(v["status"] == 200 and v["bytes"] == v["disk_bytes"]
                  for v in http.values()),
          "; ".join(f"{k}:{v['status']}/{v['bytes']}" for k, v in http.items()))

    pairs = [("foe-full-original.png", CONCEPT / "Full_body_character_concept_ar_2026-11-07T11-02-32.png"),
             ("foe-redraw.png", CONCEPT / "Same_single_character__identic_2026-11-07T11-03-25.png"),
             ("玩家V4b-对手怪V1-概念对照.png", SRC / "玩家V4b-对手怪V1-概念对照.png")]
    same = all(sha(HERE / dst) == sha(src) for dst, src in pairs)
    check("copies_match_sources_byte_for_byte", same,
          "; ".join(f"{d}:{sha(HERE / d)[:8]}" for d, _ in pairs))

    board, detail = STATS["board"], STATS["detail"]
    bp, dp = HERE / board["file"], HERE / detail["file"]
    check("design_stats_self_consistent",
          list(Image.open(bp).size) == board["size"]
          and bp.stat().st_size == board["bytes"]
          and colors(bp) == board["colors_120"]
          and list(Image.open(dp).size) == detail["size"]
          and dp.stat().st_size == detail["bytes"]
          and colors(dp) == detail["colors_120"],
          f"board={board['size']} detail={detail['size']}")

    w = STATS["wipe_watermark"]
    check("watermark_wipe_evidenced",
          w["dark_ratio_before"] < 0.01 and w["off_fill_before"] > 0.005
          and w["off_fill_after"] < 0.01,
          f"dark={w['dark_ratio_before']} off_fill={w['off_fill_before']}→{w['off_fill_after']}")

    crops = STATS["crops"]
    boxes_ok = all(0 <= b[0] < b[2] <= 1 and 0 <= b[1] < b[3] <= 1
                   for b in (c["relative_box"] for c in crops))
    check("six_crops_distinct_and_in_range",
          len(crops) == 6 and len({c["key"] for c in crops}) == 6 and boxes_ok,
          f"keys={[c['key'] for c in crops]}")

    shown = STATS["board"]["shown_crops"]
    check("board_shown_crops_are_a_subset",
          len(shown) == 4 and set(shown) <= {c["key"] for c in crops},
          f"shown={shown}")

    check("board_and_detail_not_blank",
          colors(bp) > 300 and colors(dp) > 300,
          f"colors={colors(bp)}/{colors(dp)}")

    passed = sum(1 for _, o, _ in checks if o)
    verdict = "SHOWCASE_VERIFIED" if passed == len(checks) else "SHOWCASE_CHECK_FAILED"
    text = "\n".join(f"{'PASS' if o else 'FAIL'}  {n}  {d}" for n, o, d in checks)
    text += f"\n\n{passed}/{len(checks)} PASS  {verdict}\n"
    LOG.write_text(text, encoding="utf-8")
    RESULT.write_text(json.dumps(
        {"verdict": verdict, "passed": passed, "total": len(checks),
         "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(text)
    raise SystemExit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
