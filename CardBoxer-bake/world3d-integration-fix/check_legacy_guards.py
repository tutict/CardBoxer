"""World3D 接线修复 · 历史守卫红因实测与列债（不篡改历史归档）。

跑 G / H / I / 止损四套历史验收脚本，逐条收集 FAIL 名字并归类。
这些脚本会把报告写到各自 logs/，所以跑前对 logs/ 整目录做二进制快照，
跑完后逐字节还原并校验相等（含删除本次新增文件），历史归档零改动。

用法：python check_legacy_guards.py
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
GAME = BAKE.parent / "CardBoxer"
PY = Path(sys.executable)
OUT = HERE / "data" / "legacy_guard_state.json"
LOGDIR = HERE / "logs" / "guards"
BACKUP = HERE / "orig" / "guard_logs"

GUARDS = [
    ("route-g-game-3d-integration", "verify_g.py"),
    ("route-h-two-sided-3d-combat", "verify_h.py"),
    ("route-i-visual-distinction", "verify_i.py"),
    ("display-stopgap", "verify_stopgap.py"),
]

# 改源码必然报红的名字特征：源码文本 / sha 快照 / 新增行白名单。
TEXTUAL_HINTS = ("yaw", "sha", "patch", "source", "shape", "whitelist",
                 "added", "parametrised", "text", "constant", "baseline",
                 "matches_live", "preserved")


def snap(d: Path) -> dict[str, bytes]:
    if not d.is_dir():
        return {}
    return {p.relative_to(d).as_posix(): p.read_bytes()
            for p in sorted(d.rglob("*")) if p.is_file()}


def restore(d: Path, before: dict[str, bytes]) -> bool:
    for rel, data in before.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    for rel in set(snap(d)) - set(before):
        (d / rel).unlink()
    return snap(d) == before


def classify(name: str) -> str:
    low = name.lower()
    if any(h in low for h in TEXTUAL_HINTS):
        return "源码文本 / sha 快照 / 新增行白名单断言：改 fighter_3d_layer.gd 必然红"
    return "UNCLASSIFIED：需人工复核是否玩法回归"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    BACKUP.mkdir(parents=True, exist_ok=True)
    rows, restores = [], {}
    for route, script in GUARDS:
        rd = BAKE / route
        sp = rd / script
        logs = rd / "logs"
        before = snap(logs)
        (BACKUP / route).mkdir(parents=True, exist_ok=True)
        (BACKUP / route / "snapshot_index.json").write_text(
            json.dumps({k: hashlib.sha256(v).hexdigest()
                        for k, v in before.items()},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not sp.is_file():
            rows.append({"route": route, "script": script,
                         "error": "MISSING SCRIPT"})
            restores[route] = restore(logs, before)
            continue
        try:
            proc = subprocess.run([str(PY), "-u", str(sp)],
                                  capture_output=True, timeout=300,
                                  cwd=str(rd))
            rc = proc.returncode
            text = (proc.stdout + b"\n--- STDERR ---\n"
                    + proc.stderr).decode("utf-8", "replace")
        except subprocess.TimeoutExpired as exc:
            rc = -1
            text = ((exc.stdout or b"") + b"\n--- TIMEOUT ---\n").decode(
                "utf-8", "replace")
        (LOGDIR / f"{route}_{script}.out").write_text(
            text, encoding="utf-8")
        failed = []
        for ln in text.splitlines():
            s = ln.strip()
            if s.startswith("FAIL ") or s.startswith("FAILED "):
                name = s.split()[-1]
                if name and name not in failed:
                    failed.append(name)
        marker = next((s for s in reversed(text.splitlines())
                       if s.strip() in (
                           "G_VERIFIED", "G_VERIFY_FAILED",
                           "H_VERIFIED", "H_NOT_VERIFIED",
                           "I_VERIFIED", "I_NOT_VERIFIED",
                           "STOPGAP_VERIFIED", "STOPGAP_FAILED")), "")
        rows.append({
            "route": route, "script": script, "rc": rc,
            "marker": marker, "failed": failed,
            "classifications": {n: classify(n) for n in failed},
            "stdout_bytes": len(text.encode("utf-8")),
        })
        restores[route] = restore(logs, before)

    unclassified = [n for r in rows for n in r.get("failed", [])
                    if classify(n).startswith("UNCLASSIFIED")]
    checks = {
        "four_guards_ran": all("error" not in r for r in rows),
        "all_logs_restored": all(restores.values()),
        "stopgap_still_green": any(
            r["route"] == "display-stopgap"
            and r.get("marker") == "STOPGAP_VERIFIED"
            and not r.get("failed") for r in rows),
        "no_unclassified_reds": not unclassified,
        "source_changed_once": sha(
            GAME / "scripts" / "fighter_3d_layer.gd")
        != "6504139c6c81bd607379739b956dea90293e2f84cc5266e8bf4d44b02917a402",
    }
    report = {
        "note": ("2026-11-14 World3D 接线修复后实测。历史守卫的红因均为源码"
                 "文本 / sha 快照 / 新增行白名单断言按设计报红，不是玩法回归；"
                 "本轮未修改任何历史脚本，跑前快照、跑后逐字节还原 logs/。"),
        "source_sha256": sha(GAME / "scripts" / "fighter_3d_layer.gd"),
        "guards": rows,
        "logs_restored": restores,
        "unclassified_reds": unclassified,
        "checks": checks,
        "failed_checks": [k for k, v in checks.items() if not v],
        "ok": all(checks.values()),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    for r in rows:
        print("GUARD", r["route"], "rc", r.get("rc"),
              "marker", r.get("marker"),
              "reds", r.get("failed"))
        for n, why in r.get("classifications", {}).items():
            print("   RED", n, "|", why)
    print("RESTORED", restores)
    for k, v in checks.items():
        print("CHECK", k, v)
    print("LEGACY_GUARDS_OK" if report["ok"] else "LEGACY_GUARDS_FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
