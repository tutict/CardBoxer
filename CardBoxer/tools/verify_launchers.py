"""Verify that the Windows launcher rejects Godot's zero-exit startup failures."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def check_case(engine, name, script):
    with tempfile.TemporaryDirectory(prefix="cardboxer-launcher-check-") as directory:
        project = Path(directory).resolve()
        if not project.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise RuntimeError("Test project escapes the temporary directory")
        (project / "tools").mkdir()
        shutil.copy2(Path(__file__).with_name("launch.ps1"), project / "tools/launch.ps1")
        (project / ".godot").mkdir()
        (project / ".godot/global_script_class_cache.cfg").write_text("list=[]\n", encoding="utf-8")
        (project / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Launcher check"\n'
            'run/main_scene="res://main.tscn"\n[rendering]\n'
            'renderer/rendering_method="gl_compatibility"\n', encoding="utf-8")
        (project / "main.tscn").write_text(
            '[gd_scene load_steps=2 format=3]\n'
            '[ext_resource type="Script" path="res://main.gd" id="1"]\n'
            '[node name="Main" type="Node3D"]\nscript = ExtResource("1")\n', encoding="utf-8")
        (project / "main.gd").write_text(script, encoding="utf-8")
        environment = os.environ.copy()
        environment["CARD_BOXER_GODOT"] = str(engine)
        process = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(project / "tools/launch.ps1"), "-Check"],
            cwd=project, env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=60)
        output = process.stdout.decode("utf-8", errors="replace")
        passed = process.returncode != 0
        if name == "script-error":
            passed = passed and "SCRIPT ERROR:" in output
        print(("PASS " if passed else "FAIL ") + name, flush=True)
        if not passed:
            print(output, flush=True)
        return {"case": name, "passed": passed, "exit_code": process.returncode}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--godot", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("These checks require Windows.")
    results = [
        check_case(args.godot.resolve(), "script-error", "extends Node3D\nthis is invalid GDScript\n"),
        check_case(args.godot.resolve(), "missing-native-models", "extends Node3D\n"),
    ]
    print(json.dumps({"passed": sum(item["passed"] for item in results), "total": len(results), "results": results}), flush=True)
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
