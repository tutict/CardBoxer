"""One-shot text-to-3D feasibility probe for the CardBoxer character.

Runs the built-in generator ONCE, downloads every returned artifact locally,
writes a model-viewer page and a machine-readable probe_report.json, and prints
a short summary. The credential is read from the environment and is never
written to disk or printed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Local copy produced by patch_generator.py: identical to the bundled script
# except that its client-side credential-prefix check also accepts tk_ keys.
SKILL = str(HERE / "generator_local.py")
TOKEN = os.environ.get("MM_TOKEN", "")
PROMPT = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()

if not TOKEN:
    print("PROBE_FAILED missing credential", flush=True)
    raise SystemExit(2)

cmd = [
    sys.executable, "-u", SKILL, "3d", PROMPT,
    "--enable-pbr", "--face-count", "80000",
    "--result-format", "FBX", "--token", TOKEN,
    "--max-poll-time", "480",
]
print("PROBE_START", flush=True)
try:
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=560)
except subprocess.TimeoutExpired as exc:
    (HERE / "gen_stdout.json").write_text(exc.stdout or "", encoding="utf-8")
    print("PROBE_FAILED timeout (job may still be running; use status)", flush=True)
    raise SystemExit(3)

(HERE / "gen_stdout.json").write_text(p.stdout, encoding="utf-8")
(HERE / "gen_stderr.log").write_text(p.stderr, encoding="utf-8")
print(f"GEN_RC {p.returncode}", flush=True)
for line in (p.stderr or "").splitlines()[-8:]:
    print("  " + line, flush=True)

try:
    out = json.loads(p.stdout)
except json.JSONDecodeError:
    print("PROBE_FAILED non-JSON stdout:", p.stdout[:500], flush=True)
    raise SystemExit(4)

if out.get("error"):
    print(f"PROBE_FAILED {out['error']}: {out.get('message','')}", flush=True)
    raise SystemExit(5)


def collect_urls(node, found):
    """The service may return a list, a dict, or a single URL, nested."""
    if isinstance(node, str):
        s = node.strip()
        if s.startswith("http://") or s.startswith("https://"):
            found.append(s)
    elif isinstance(node, dict):
        for v in node.values():
            collect_urls(v, found)
    elif isinstance(node, (list, tuple)):
        for v in node:
            collect_urls(v, found)


urls: list[str] = []
collect_urls(out, urls)
seen, ordered = set(), []
for u in urls:
    if u not in seen:
        seen.add(u)
        ordered.append(u)
print(f"RESULT_URLS {len(ordered)}", flush=True)


def guess_ext(data: bytes, url: str) -> str:
    if data[:4] == b"glTF":
        return ".glb"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"PK":
        return ".zip"
    if b"Kaydara FBX Binary" in data[:64]:
        return ".fbx"
    if re.match(rb"^(v |# |mtllib|o )", data[:64]):
        return ".obj"
    path = url.split("?")[0]
    m = re.search(r"\.([A-Za-z0-9]{2,5})$", path)
    return "." + m.group(1).lower() if m else ".bin"


saved = []
for i, url in enumerate(ordered, 1):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WorkBuddy/1.0"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
        ext = guess_ext(data, url)
        name = f"artifact_{i:02d}{ext}"
        path = HERE / name
        path.write_bytes(data)
        saved.append({
            "file": name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "source_url_path": url.split("?")[0].split("/")[-1][:120],
        })
        print(f"DOWNLOADED {name} {len(data)} B", flush=True)
    except Exception as exc:
        print(f"DOWNLOAD_FAILED {url[:100]} {type(exc).__name__}: {exc}", flush=True)

# A model-viewer page next to the GLB so the built-in preview can show it.
glb = next((s["file"] for s in saved if s["file"].endswith(".glb")), None)
viewer_name = None
if glb:
    ts = time.strftime("%Y%m%d-%H%M%S")
    viewer_name = f"generated_model_{ts}_viewer.html"
    html = f"""<!doctype html>
<html lang="zh">
<head><meta charset="utf-8"><title>CardBoxer 3D 模型探针</title>
<script type="module" src="https://ajax.googleapis.com/ajax/libs/model-viewer/4.0.0/model-viewer.min.js"></script>
<style>body{{margin:0;background:#f4f5f7;font-family:sans-serif}}
model-viewer{{width:100vw;height:86vh}}
.bar{{padding:10px 16px;color:#222;font-size:14px}}</style></head>
<body><div class="bar">二游风 3D 拳手 · 探针产物 · 可拖拽旋转 / 滚轮缩放</div>
<model-viewer src="{glb}" camera-controls auto-rotate shadow-intensity="1"
 environment-image="neutral" exposure="1.0"></model-viewer>
</body></html>"""
    (HERE / viewer_name).write_text(html, encoding="utf-8")

report = {
    "job_id": out.get("job_id"),
    "status": out.get("status"),
    "raw_result": out.get("raw_result"),
    "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
    "settings": {"enable_pbr": True, "face_count": 80000, "result_format": "FBX",
                 "model": "3.1", "generate_type": "Normal(default)"},
    "artifacts": saved,
    "glb": glb,
    "viewer_html": viewer_name,
}
(HERE / "probe_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"PROBE_OK artifacts={len(saved)} glb={glb} viewer={viewer_name}", flush=True)
