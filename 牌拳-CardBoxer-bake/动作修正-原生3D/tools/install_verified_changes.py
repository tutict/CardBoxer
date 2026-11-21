"""Install only reviewed changed files, with snapshot guards and full rollback.

Default is a dry run. The main project is named explicitly by the approved plan.
No deletion, git reset, cleanup, or unrelated file replacement is performed.
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

TASK = Path(__file__).resolve().parent.parent
PROJECT = TASK / "project"
TARGET = Path("C:/Users/tutic/Desktop/学习资料/牌拳-CardBoxer")
GODOT = Path("C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contained(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise RuntimeError(f"Unsafe relative path: {relative}")
    result = (root / rel).resolve()
    if not result.is_relative_to(root.resolve()):
        raise RuntimeError(f"Target escapes its named project: {result}")
    return result


def prepare() -> list[dict]:
    snapshot = json.loads((TASK / "baseline-manifest.json").read_text(encoding="utf-8-sig"))
    if Path(snapshot["source"]).resolve() != TARGET.resolve():
        raise RuntimeError("Install target differs from the approved source snapshot")
    baseline = {row["path"]: row["sha256"] for row in snapshot["files"]}
    rows = json.loads((TASK / "reports/change-manifest.json").read_text(encoding="utf-8"))
    allowed = {".gd", ".uid", ".json", ".glb", ".import", ".bat", ".md"}
    for row in rows:
        relative = row["path"]
        source = contained(PROJECT, relative)
        destination = contained(TARGET, relative)
        if source.suffix not in allowed or ".godot" in Path(relative).parts:
            raise RuntimeError(f"Unexpected source file: {relative}")
        if digest(source) != row["after"]:
            raise RuntimeError(f"Review manifest is stale: {relative}")
        expected = baseline.get(relative)
        actual = digest(destination) if destination.exists() else None
        if actual != expected:
            raise RuntimeError(f"Main project changed since snapshot; preserve it: {relative}")
        row["target"] = str(destination)
    return rows


def verify_engine() -> list[dict]:
    checks = [(None, "import", None),
              ("tests/native_motion_check.gd", "native-motion", "NATIVE MOTION CHECK: PASS"),
              ("tests/native_rig_check.gd", "native-rig", "NATIVE_RIG_CHECK: PASS"),
              ("tests/battle_presentation_check.gd", "presentation", "BATTLE PRESENTATION CHECK:"),
              ("tests/battle_integration_check.gd", "integration", "BATTLE INTEGRATION CHECK:"),
              ("tests/battle_transition_check.gd", "transitions", "BATTLE TRANSITION CHECK:"),
              ("tests/battle_contact_spacing_check.gd", "contact", "BATTLE CONTACT SPACING CHECK:"),
              ("tests/motion_check.gd", "2d-motion", "MOTION CHECK: PASS"),
              ("scripts/combo_check.gd", "combo", "COMBO CHECK: 8/8 passed"),
              ("tests/taikou_rules_check.gd", "rules", "TAIKOU RULES CHECK: 90/90 passed")]
    if (TARGET / "tests/natural_runtime_check.gd").is_file():
        checks.append(("tests/natural_runtime_check.gd", "natural-runtime",
                       "NATURAL RUNTIME CHECK:"))
    results = []
    for script, tag, marker in checks:
        log = TASK / "logs" / f"installed-{tag}-engine.log"
        cmd = [str(GODOT), "--headless", "--path", str(TARGET), "--log-file", str(log)]
        if script:
            cmd += ["--script", "res://" + script]
        else:
            cmd += ["--editor", "--import"]
        environment = os.environ.copy()
        for key in ("CARD_BOXER_3D", "CARD_BOXER_BATTLE_MODE", "CARD_BOXER_BOT",
                    "CARD_BOXER_TAIKOU_BOT", "CARD_BOXER_CAPTURE", "CARD_BOXER_CAPTURE_AT"):
            environment.pop(key, None)
        done = subprocess.run(cmd, env=environment, capture_output=True, timeout=180,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        output = done.stdout.decode("utf-8", errors="replace") + done.stderr.decode("utf-8", errors="replace")
        (TASK / "logs" / f"installed-{tag}-output.log").write_text(output, encoding="utf-8")
        script_error = any(text in output for text in
                           ("SCRIPT ERROR:", "Parse Error:", "Failed to load script"))
        ok = done.returncode == 0 and not script_error and (marker is None or marker in output)
        results.append({"check": tag, "ok": ok, "exit_code": done.returncode,
                        "log": str(log)})
        print(f"Installed {tag}: {'PASS' if ok else 'FAIL'}", flush=True)
        if not ok:
            (TASK / "reports/installed-checks.json").write_text(
                json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
            raise RuntimeError(f"Installed verification failed: {tag}; see output log")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    rows = prepare()
    preview = {"target": str(TARGET), "files": rows, "dry_run": not args.apply}
    (TASK / "reports/install-preview.json").write_text(
        json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'Installing' if args.apply else 'Dry run'} {len(rows)} guarded files", flush=True)
    if args.apply:
        backup = TASK / "installed-backup"
        if backup.exists():
            raise RuntimeError("Install backup already exists; refusing to overwrite a recovery point")
        backup.mkdir()
        receipt = {"target": str(TARGET), "time": datetime.datetime.now().isoformat(), "files": []}
        for row in rows:
            relative = row["path"]
            source = contained(PROJECT, relative)
            destination = contained(TARGET, relative)
            current = digest(destination) if destination.exists() else None
            if current != row["before"]:
                raise RuntimeError(f"Main file changed during installation; preserve it: {relative}")
            if destination.exists():
                saved = contained(backup, relative)
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, saved)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".native-motion-new")
            if temporary.exists():
                raise RuntimeError(f"Unrelated temporary file already exists: {temporary}")
            shutil.copy2(source, temporary)
            if digest(temporary) != row["after"]:
                raise RuntimeError(f"Temporary copy verification failed: {relative}")
            os.replace(temporary, destination)
            if digest(destination) != row["after"]:
                raise RuntimeError(f"Install verification failed: {relative}")
            receipt["files"].append(row)
            (TASK / "reports/install-receipt.json").write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.verify:
            checks = verify_engine()
            (TASK / "reports/installed-checks.json").write_text(
                json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
        print("INSTALL_COMPLETE: guarded copies verified, rollback backup saved", flush=True)
