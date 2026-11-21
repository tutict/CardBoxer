"""断连后只查原 job，不重提：image-to-3D 的产物回收器。

job_id 从 probe_run.log 的 `Job <id>:` 正则提取（gen_stdout.json 在
CONNECTION_ERROR 时只有 error/message，不带 id），不硬编码、不猜。
凭据从 MM_TOKEN 环境变量读，不写盘、不打印。
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
BAKE = HERE.parent
GEN = str(HERE / "generator_local.py")
TOKEN = os.environ.get("MM_TOKEN", "")
IMAGE = BAKE / "对手怪2D设计展示" / "foe-full-clean.png"
MAX_QUERIES = 110
INTERVAL = 5

log_text = (HERE / "probe_run.log").read_text(encoding="utf-8")
m = re.search(r"Job (\d+):", log_text)
assert m, "no job_id found in probe_run.log (nothing was submitted)"
JOB = m.group(1)
if not TOKEN:
    print("RESUME_FAILED missing credential", flush=True)
    raise SystemExit(2)
print(f"RESUME_START job_id={JOB} (query only, no resubmit)", flush=True)


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
        if s.startswith(("http://", "https://")):
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
    mm = re.search(r"\.([A-Za-z0-9]{2,5})$", url.split("?")[0])
    return "." + mm.group(1).lower() if mm else ".bin"


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
    if out.get("error"):
        transient += 1
        log(f"QUERY {i} transient {out['error']}: {out.get('message','')[:100]}")
        time.sleep(INTERVAL)
        continue
    status = str(out.get("status", ""))
    log(f"QUERY {i} status={status} elapsed={round(time.time()-t0)}s")
    if status in ("DONE", "FAIL"):
        raw_final = out
        break
    time.sleep(INTERVAL)

if raw_final is None or status != "DONE":
    log(f"RESUME_FAILED status={status} last={str(raw_final)[:400]}")
    raise SystemExit(3)

urls: list[str] = []
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
        name = f"artifact_{i:02d}{guess_ext(data, url)}"
        (HERE / name).write_bytes(data)
        saved.append({"file": name, "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest(),
                      "source_url_path": url.split("?")[0].split("/")[-1][:120]})
        log(f"DOWNLOADED {name} {len(data)} B")
    except Exception as exc:
        log(f"DOWNLOAD_FAILED {url[:90]} {type(exc).__name__}: {exc}")

glb = next((s["file"] for s in saved if s["file"].endswith(".glb")), None)
viewer = None
if glb:
    ts = time.strftime("%Y%m%d-%H%M%S")
    viewer = f"generated_model_{ts}_viewer.html"
    (HERE / viewer).write_text(f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><title>《牌拳》对手怪 V1 · 3D 模型</title>
<script type="module" src="https://ajax.googleapis.com/ajax/libs/model-viewer/4.0.0/model-viewer.min.js"></script>
<style>body{{margin:0;background:#f4f5f7;font-family:sans-serif}}
model-viewer{{width:100vw;height:86vh}}
.bar{{padding:10px 16px;color:#222;font-size:14px}}</style></head>
<body><div class="bar">《牌拳》对手怪 V1 · 图生 3D 模型 · 可拖拽旋转 / 滚轮缩放</div>
<model-viewer src="{glb}" camera-controls auto-rotate shadow-intensity="1"
 environment-image="neutral" exposure="1.0"></model-viewer>
</body></html>""", encoding="utf-8")

report = {
    "mode": "image-to-3D",
    "job_id": JOB,
    "status": status,
    "resumed_after_connection_drop": True,
    "transient_queries": transient,
    "submit_poll_failure": "CONNECTION_ERROR at elapsed=21s (job was already RUN)",
    "input_image": {"file": IMAGE.relative_to(BAKE).as_posix(),
                    "bytes": IMAGE.stat().st_size,
                    "sha256": hashlib.sha256(IMAGE.read_bytes()).hexdigest()},
    "prompt": None,
    "settings": {"enable_pbr": True, "face_count": 80000, "result_format": "FBX",
                 "model": "3.1", "generate_type": "Normal(default)"},
    "artifacts": saved,
    "glb": glb,
    "viewer_html": viewer,
}
(HERE / "probe_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
log(f"RESUME_OK artifacts={len(saved)} glb={glb} viewer={viewer} "
    f"elapsed={round(time.time()-t0)}s")
