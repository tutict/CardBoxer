"""Resume ONE already-submitted 3D job after a polling connection drop.

The submit call authenticated and returned job 1510546865849843712 (RUN), then
the poller lost its connection. Per the skill's retry rules we must NOT submit
again: query only this job id until DONE, then download every artifact.

The credential is read from MM_TOKEN and never written to disk or printed.
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
GEN = str(HERE / "generator_local.py")
JOB = "1510546865849843712"
TOKEN = os.environ.get("MM_TOKEN", "")
PROMPT = (HERE / "prompt.txt").read_text(encoding="utf-8").strip()
MAX_QUERIES = 110
INTERVAL = 5

if not TOKEN:
    print("RESUME_FAILED missing credential", flush=True)
    raise SystemExit(2)


def log(*a):
    print(*a, flush=True)


def query():
    p = subprocess.run(
        [sys.executable, "-u", GEN, "status", JOB, "--type", "3d", "--token", TOKEN],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=90,
    )
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"error": "NON_JSON", "message": (p.stdout or "")[:200],
                "stderr_tail": (p.stderr or "")[-200:]}


def collect_urls(node, found):
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
    m = re.search(r"\.([A-Za-z0-9]{2,5})$", url.split("?")[0])
    return "." + m.group(1).lower() if m else ".bin"


raw_final = None
status = "UNKNOWN"
transient = 0
t0 = time.time()
for i in range(1, MAX_QUERIES + 1):
    try:
        out = query()
    except Exception as exc:
        transient += 1
        log(f"QUERY {i} transient {type(exc).__name__}")
        time.sleep(INTERVAL)
        continue
    status = str(out.get("status", ""))
    if out.get("error"):
        transient += 1
        log(f"QUERY {i} transient {out['error']}: {out.get('message','')[:100]}")
        time.sleep(INTERVAL)
        continue
    log(f"QUERY {i} status={status} elapsed={round(time.time()-t0)}s")
    if status == "DONE":
        raw_final = out
        break
    if status == "FAIL":
        raw_final = out
        break
    time.sleep(INTERVAL)

if raw_final is None or status != "DONE":
    log(f"RESUME_FAILED status={status} last={str(raw_final)[:400]}")
    raise SystemExit(3)

urls = []
collect_urls(raw_final, urls)
seen, ordered = set(), []
for u in urls:
    if u not in seen:
        seen.add(u)
        ordered.append(u)
log(f"RESULT_URLS {len(ordered)} transient_queries={transient}")

saved = []
for i, url in enumerate(ordered, 1):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "WorkBuddy/1.0"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
        ext = guess_ext(data, url)
        name = f"artifact_{i:02d}{ext}"
        (HERE / name).write_bytes(data)
        saved.append({
            "file": name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "source_url_path": url.split("?")[0].split("/")[-1][:120],
        })
        log(f"DOWNLOADED {name} {len(data)} B")
    except Exception as exc:
        log(f"DOWNLOAD_FAILED {url[:90]} {type(exc).__name__}: {exc}")

glb = next((s["file"] for s in saved if s["file"].endswith(".glb")), None)
viewer_name = None
if glb:
    ts = time.strftime("%Y%m%d-%H%M%S")
    viewer_name = f"generated_model_{ts}_viewer.html"
    html = f"""<!doctype html>
<html lang="zh">
<head><meta charset="utf-8"><title>CardBoxer 造型 V2 · 3D 模型</title>
<script type="module" src="https://ajax.googleapis.com/ajax/libs/model-viewer/4.0.0/model-viewer.min.js"></script>
<style>body{{margin:0;background:#f4f5f7;font-family:sans-serif}}
model-viewer{{width:100vw;height:86vh}}
.bar{{padding:10px 16px;color:#222;font-size:14px}}</style></head>
<body><div class="bar">白色云纹长衫 · 无拳套 · 造型 V2 · 可拖拽旋转 / 滚轮缩放</div>
<model-viewer src="{glb}" camera-controls auto-rotate shadow-intensity="1"
 environment-image="neutral" exposure="1.0"></model-viewer>
</body></html>"""
    (HERE / viewer_name).write_text(html, encoding="utf-8")

report = {
    "job_id": JOB,
    "status": status,
    "resumed_after_connection_drop": True,
    "transient_queries": transient,
    "raw_result": raw_final.get("raw_result", raw_final),
    "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
    "settings": {"enable_pbr": True, "face_count": 80000,
                 "result_format": "FBX", "model": "3.1",
                 "generate_type": "Normal(default)"},
    "artifacts": saved,
    "glb": glb,
    "viewer_html": viewer_name,
}
(HERE / "probe_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"RESUME_OK artifacts={len(saved)} glb={glb} viewer={viewer_name} "
    f"elapsed={round(time.time()-t0)}s")
