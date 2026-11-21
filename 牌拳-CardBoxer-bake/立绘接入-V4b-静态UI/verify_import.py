"""核验 Godot 生成的 8 份 .import：uid 唯一、路径自洽、.ctex 存在且非空。

同时证明既有 5 份 .import 与源码基线逐字节一致（没有被编辑器顺手改写）。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
GAME = Path(r"C:\Users\tutic\Desktop\学习资料\牌拳-CardBoxer")
DST = GAME / "assets" / "portraits"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def parse_import(p: Path) -> dict:
    txt = p.read_text(encoding="utf-8")
    out = {}
    for key in ("importer", "type", "uid", "path", "source_file"):
        m = re.search(r'^' + key + r'="?([^"\n]+)"?\s*$', txt, re.M)
        out[key] = m.group(1).strip('"') if m else None
    m = re.search(r"dest_files=\[\s*\"([^\"]+)\"", txt)
    out["dest_first"] = m.group(1) if m else None
    return out


def main() -> None:
    manifest = json.loads((HERE / "assets_manifest.json").read_text(encoding="utf-8"))
    names = [r["file"] for r in manifest["outputs"]]
    rows = []
    all_uids = []
    for name in names:
        imp = DST / (name + ".import")
        png = DST / name
        if not imp.is_file():
            rows.append({"file": name, "ok": False, "reason": "missing .import"})
            continue
        meta = parse_import(imp)
        ctex_rel = (meta["path"] or "").replace("res://", "")
        ctex = GAME / ctex_rel
        md5 = ctex.with_suffix(".md5")
        all_uids.append(meta["uid"])
        checks = {
            "png_exists": png.is_file(),
            "importer_texture": meta["importer"] == "texture",
            "type_compressed": meta["type"] == "CompressedTexture2D",
            "uid_present": bool(meta["uid"] and meta["uid"].startswith("uid://")),
            "source_file_ok": meta["source_file"] == f"res://assets/portraits/{name}",
            "path_matches_dest": meta["path"] == (meta["dest_first"] or ""),
            "ctex_exists": ctex.is_file(),
            "ctex_nonempty": ctex.is_file() and ctex.stat().st_size > 0,
            "md5_exists": md5.is_file(),
        }
        rows.append({
            "file": name,
            "uid": meta["uid"],
            "ctex": ctex_rel,
            "ctex_bytes": ctex.stat().st_size if ctex.is_file() else 0,
            "checks": checks,
            "ok": all(checks.values()),
        })

    # 全局 uid 唯一（含既有 5 份）。rows 里已经收过新 8 份，
    # 这里只遍历「不在 assets/portraits/ 下」的既有 .import，避免重复计数。
    existing = sorted(p for p in GAME.rglob("*.import") if p.parent != DST)
    for p in existing:
        meta = parse_import(p)
        if meta["uid"]:
            all_uids.append(meta["uid"])
    uid_unique = len(all_uids) == len(set(all_uids))

    # 既有文件未被改写
    baseline = json.loads((HERE / "源码基线.json").read_text(encoding="utf-8"))["files"]
    base = {r["path"]: r["sha256"] for r in baseline}
    # 本轮有意修改的既有文件；其余一律必须与基线逐字节一致。
    # tests/redraw_gate_check.gd 修的是「randi 洗牌导致 1/30 假红」的既有抖动。
    intentional = {"scripts/hud.gd", "tests/redraw_gate_check.gd"}
    drift = []
    for rel, expect in base.items():
        if rel in intentional:
            continue
        p = GAME / rel
        if not p.is_file() or sha256(p) != expect:
            drift.append(rel)

    result = {
        "imports": rows,
        "all_imports_ok": all(r["ok"] for r in rows),
        "uid_unique": uid_unique,
        "uid_count": len(all_uids),
        "existing_import_count": len(existing),
        "baseline_drift": drift,
        "baseline_clean": len(drift) == 0,
        "intentional_changes": sorted(intentional),
    }
    (HERE / "verify_import.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for r in rows:
        print(f"{r['file']:22s} ok={r['ok']} uid={r.get('uid')} ctex_bytes={r.get('ctex_bytes')}")
    print(f"UID_UNIQUE={uid_unique} ({len(all_uids)} uids)")
    print(f"BASELINE_DRIFT={len(drift)} {drift[:8]}")
    print("IMPORT_VERIFIED" if result["all_imports_ok"] and uid_unique and result["baseline_clean"]
          else "IMPORT_FAILED")


if __name__ == "__main__":
    main()
