"""把已定稿的对手怪 2D 概念图变成 3D 模型（image-to-3D），只提交一次。

与文生 3D 的区别：
  * 输入是 `对手怪2D设计展示/foe-full-clean.png`（抹掉服务水印的正面全身），
    造型由图像决定，不另写 prompt —— 避免 V5 那种「文字语义簇把造型带偏」。
  * base64 约 2.59M 字符，超过 Windows CreateProcess 32767 字符上限，
    所以走本地兼容副本新增的 `--image-base64-file`，不塞进命令行。
  * 产物按**文件魔数**分类，服务返回 URL 编号顺序历史上变过四次。

凭据只从环境变量读，不写盘、不打印。失败如实记录，不伪造产物。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
IMAGE = BAKE / "对手怪2D设计展示" / "foe-full-clean.png"
SKILL = HERE / "generator_local.py"
B64 = HERE / "_image_b64.txt"
TOKEN = os.environ.get("MM_TOKEN", "")

if not TOKEN:
    print("PROBE_FAILED missing credential", flush=True)
    raise SystemExit(2)
assert IMAGE.is_file(), f"missing concept image: {IMAGE}"

raw = IMAGE.read_bytes()
with Image.open(IMAGE) as f:
    size = list(f.size)
b64 = base64.b64encode(raw).decode("ascii")
B64.write_text(b64, encoding="ascii")
print(f"INPUT_IMAGE {IMAGE.name} bytes={len(raw)} size={size} "
      f"sha256={hashlib.sha256(raw).hexdigest()} b64_chars={len(b64)}", flush=True)

cmd = [
    sys.executable, "-u", str(SKILL), "3d",
    "--image-base64-file", str(B64),
    "--enable-pbr", "--face-count", "80000",
    "--result-format", "FBX", "--token", TOKEN,
    "--max-poll-time", "480",
]
print("PROBE_START mode=image-to-3D", flush=True)
try:
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=560)
except subprocess.TimeoutExpired as exc:
    (HERE / "gen_stdout.json").write_text(exc.stdout or "", encoding="utf-8")
    print("PROBE_FAILED timeout (job may still be running; use status)", flush=True)
    raise SystemExit(3)
finally:
    B64.unlink(missing_ok=True)   # 2.6MB 中间文件，不留在归档里

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
    m = re.search(r"\.([A-Za-z0-9]{2,5})$", url.split("?")[0])
    return "." + m.group(1).lower() if m else ".bin"


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
        print(f"DOWNLOADED {name} {len(data)} B", flush=True)
    except Exception as exc:
        print(f"DOWNLOAD_FAILED {url[:100]} {type(exc).__name__}: {exc}", flush=True)

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
    "job_id": out.get("job_id"),
    "status": out.get("status"),
    "input_image": {"file": IMAGE.relative_to(BAKE).as_posix(), "size": size,
                    "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                    "watermark": "removed (foe-full-clean.png)"},
    "prompt": None,
    "prompt_rationale": "造型由图像决定，不另写文字 prompt，避免语义簇带偏",
    "settings": {"enable_pbr": True, "face_count": 80000, "result_format": "FBX",
                 "model": "3.1", "generate_type": "Normal(default)",
                 "image_base64_chars": len(b64)},
    "artifacts": saved,
    "glb": glb,
    "viewer_html": viewer,
}
(HERE / "probe_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"PROBE_OK artifacts={len(saved)} glb={glb} viewer={viewer}", flush=True)
