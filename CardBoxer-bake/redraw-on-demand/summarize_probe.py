"""从五段探针的 probe_result.json 抽出绘制耗时账，写 probe_summary.json。"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "comparison-frames"

US = ("arena_draw_us", "fx_draw_us", "hud_draw_us")
DRAWS = ("arena_draws", "fx_draws", "hud_draws")
SKIPS = ("arena_skipped", "fx_skipped", "hud_skipped")


def main() -> int:
    d = json.loads((OUT / "probe_result.json").read_text(encoding="utf-8"))
    rows = []
    for ph in d["phases"]:
        st = ph["redraw_delta"]
        row = {
            "name": ph["name"],
            "gate": ph["gate"],
            "frames": ph["frames"],
            "draws": sum(int(st[k]) for k in DRAWS),
            "skips": sum(int(st[k]) for k in SKIPS),
            "draw_us": sum(int(st[k]) for k in US),
            "per_layer_us": {k: int(st[k]) for k in US},
            "TIME_PROCESS_mean_ms": ph["process_ms"]["mean"],
        }
        rows.append(row)
        print("%-12s gate=%-5s frames=%-3d draws=%-4d skips=%-4d draw_us=%-8d %s"
              % (row["name"], row["gate"], row["frames"], row["draws"],
                 row["skips"], row["draw_us"], row["per_layer_us"]))
    off = next(r for r in rows if r["name"] == "off")
    on = next(r for r in rows if r["name"] == "on")
    payload = {
        "rows": rows,
        "static_saved_draw_us": off["draw_us"] - on["draw_us"],
        "static_saved_draws": off["draws"] - on["draws"],
        "TIME_PROCESS_note": "retired: window throttle makes it bimodal (see logs/probe.log)",
    }
    (OUT / "probe_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("STATIC SAVED draw_us=%d draws=%d" %
          (payload["static_saved_draw_us"], payload["static_saved_draws"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
