"""Verify a Blender 5.2.3 portable install can take over the CardBoxer bake chain.

Judgement criteria (in order):
  1. Version strings really differ (5.2.0 vs 5.2.3), both are LTS.
  2. Re-running boxer_bake2.py with 5.2.3 produces the SAME BYTES as the 5.2.0
     baseline produced in this session (which itself is byte-identical to the
     archived baked2.json). Text logs are NOT a criterion: this session proved
     the printed `held` / `k` / stance-gap stats drift while the JSON does not.
  3. If bytes differ, report the exact numeric drift instead of hiding it.
  4. headless EEVEE really writes a transparent PNG on the new version
     (this is the capability B-route sprite rendering depends on).
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

OLD = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
BAKE_SCRIPT = r"D:\Projects\CardBoxer\CardBoxer-bake\boxer_bake2.py"
ARCHIVE_JSON = r"D:\Projects\CardBoxer\CardBoxer-bake\baked2.json"
WORK = r"C:\Users\tutic\AppData\Local\Temp\blender-upgrade\verify"
BASELINE_JSON = os.path.join(WORK, "baked-5.2.0.json")

RENDER_EXPR = """
import bpy
s = bpy.context.scene
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete()
bpy.ops.mesh.primitive_cube_add()
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
s.collection.objects.link(cam)
cam.location = (0, 0, 5)
cam.data.type = "ORTHO"
cam.data.ortho_scale = 3
s.camera = cam
bpy.ops.object.light_add(type="SUN", location=(1, -2, 4))
s.render.engine = "BLENDER_EEVEE"
s.render.resolution_x = 128
s.render.resolution_y = 128
s.render.resolution_percentage = 100
s.render.film_transparent = True
s.render.image_settings.file_format = "PNG"
s.render.filepath = r"{out}"
bpy.ops.render.render(write_still=True)
print("RENDER_OK")
"""


def run(cmd: list[str], log_name: str) -> tuple[int, str]:
    log_path = os.path.join(WORK, log_name)
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=300)
    text = proc.stdout + "\n" + proc.stderr
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return proc.returncode, text


def version(exe: str, tag: str) -> str:
    rc, text = run(
        [exe, "-b", "--factory-startup", "--python-expr",
         "import bpy;print('VERSION',bpy.app.version_string);print('BUILD',bpy.app.build_hash.decode(),bpy.app.build_date.decode())"],
        f"version-{tag}.log",
    )
    lines = [ln.strip() for ln in text.splitlines() if ln.startswith(("VERSION", "BUILD"))]
    print(f"  {tag}: rc={rc} " + " | ".join(lines), flush=True)
    return lines[0] if lines else ""


def bake(exe: str, out_path: str, tag: str) -> int:
    rc, text = run(
        [exe, "-b", "--factory-startup", "--python", BAKE_SCRIPT, "--", out_path],
        f"bake-{tag}.log",
    )
    tail = [ln.strip() for ln in text.splitlines() if "wrote " in ln or "SCRIPT ERROR" in ln or "Error" in ln]
    print(f"  {tag}: rc={rc} " + " | ".join(tail[-3:]), flush=True)
    return rc


def numeric_diff(a, b, path: str = "") -> list[tuple[str, object, object]]:
    out: list[tuple[str, object, object]] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            out.extend(numeric_diff(a.get(key), b.get(key), f"{path}.{key}"))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((path + ".len", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(numeric_diff(x, y, f"{path}[{i}]"))
    elif a != b:
        out.append((path, a, b))
    return out


def render(exe: str, tag: str) -> tuple[bool, str]:
    out = os.path.join(WORK, f"eevee-{tag}.png")
    expr = RENDER_EXPR.format(out=out)
    rc, text = run(
        [exe, "-b", "--factory-startup", "--python-expr", expr],
        f"render-{tag}.log",
    )
    ok = os.path.exists(out)
    size = os.path.getsize(out) if ok else 0
    png_head = b""
    if ok:
        with open(out, "rb") as handle:
            png_head = handle.read(8)
    rendered = "RENDER_OK" in text
    png_magic = b"\x89PNG\r\n\x1a\n"
    header_ok = png_head == png_magic
    verdict = rc == 0 and ok and size > 1000 and header_ok and rendered
    # One variable feeds both the verdict and the printout. An earlier version
    # printed a second, escaped literal here and showed header_ok=False while
    # the real check passed -- exactly the "log is not the criterion" trap.
    print(f"  {tag}: rc={rc} png={size}B header_ok={header_ok} RENDER_OK={rendered} -> {'OK' if verdict else 'FAIL'}", flush=True)
    return verdict, out


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify_upgrade.py <new blender.exe>")
        return 2
    new = sys.argv[1]
    os.makedirs(WORK, exist_ok=True)
    for path in (OLD, new, BAKE_SCRIPT, ARCHIVE_JSON, BASELINE_JSON):
        if not os.path.exists(path):
            print(f"FATAL missing {path}")
            return 2

    print("== 1. versions ==", flush=True)
    old_v = version(OLD, "5.2.0")
    new_v = version(new, "5.2.3")
    ok_version = "5.2.0" in old_v and "5.2.3" in new_v

    print("== 2. baseline determinism (already archived JSON vs this-session 5.2.0 rerun) ==", flush=True)
    with open(ARCHIVE_JSON, "rb") as handle:
        archive = handle.read()
    with open(BASELINE_JSON, "rb") as handle:
        baseline = handle.read()
    ok_baseline = archive == baseline
    print(f"  archive={len(archive)}B sha={hashlib.sha256(archive).hexdigest()[:16]}", flush=True)
    print(f"  baseline={len(baseline)}B sha={hashlib.sha256(baseline).hexdigest()[:16]}", flush=True)
    print(f"  BYTE_IDENTICAL={ok_baseline}", flush=True)

    print("== 3. re-bake with 5.2.3 ==", flush=True)
    new_json = os.path.join(WORK, "baked-5.2.3.json")
    ok_bake_rc = bake(new, new_json, "5.2.3") == 0
    with open(new_json, "rb") as handle:
        fresh = handle.read()
    ok_bytes = fresh == baseline
    print(f"  new={len(fresh)}B sha={hashlib.sha256(fresh).hexdigest()[:16]}", flush=True)
    print(f"  BYTE_IDENTICAL_TO_BASELINE={ok_bytes}", flush=True)
    drifts: list[tuple[str, object, object]] = []
    if not ok_bytes:
        drifts = numeric_diff(json.loads(baseline.decode("utf-8")), json.loads(fresh.decode("utf-8")))
        print(f"  numeric drift entries={len(drifts)}", flush=True)
        for path, x, y in drifts[:12]:
            print(f"    {path}: {x!r} -> {y!r}", flush=True)

    print("== 4. headless EEVEE render ==", flush=True)
    ok_old_render, _ = render(OLD, "5.2.0")
    ok_new_render, _ = render(new, "5.2.3")

    checks = {
        "version_upgrade": ok_version,
        "baseline_deterministic": ok_baseline,
        "bake_rc_0": ok_bake_rc,
        "bake_bytes_identical": ok_bytes,
        "eevee_old_ok": ok_old_render,
        "eevee_new_ok": ok_new_render,
    }
    print("== RESULT ==", flush=True)
    for key, value in checks.items():
        print(f"  {'PASS' if value else 'FAIL'}  {key}", flush=True)
    all_green = all(checks.values())
    print("UPGRADE_VERIFIED" if all_green else "UPGRADE_NOT_VERIFIED", flush=True)
    with open(os.path.join(WORK, "result.json"), "w", encoding="utf-8") as handle:
        json.dump({"checks": checks, "drift_count": len(drifts),
                   "new_sha256": hashlib.sha256(fresh).hexdigest(),
                   "baseline_sha256": hashlib.sha256(baseline).hexdigest()},
                  handle, ensure_ascii=False, indent=2)
    return 0 if all_green else 1


if __name__ == "__main__":
    raise SystemExit(main())
