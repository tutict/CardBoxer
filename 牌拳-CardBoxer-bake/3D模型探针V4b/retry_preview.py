"""补下载生成任务已返回、但首次下载 SSL 握手超时的预览 PNG。

这不是重提生成任务：job 1510561848168054784 已 DONE，URL 就在 gen_stdout.json 里。
只重试取同一个 URL，成功后按文件魔数命名，不按 URL 编号猜。
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def collect(node, found):
    if isinstance(node, str):
        if node.strip().startswith(("http://", "https://")):
            found.append(node.strip())
    elif isinstance(node, dict):
        for v in node.values():
            collect(v, found)
    elif isinstance(node, (list, tuple)):
        for v in node:
            collect(v, found)


raw = (HERE / "gen_stdout.json").read_text(encoding="utf-8")
out = json.loads(raw)
urls = []
collect(out, urls)
urls = list(dict.fromkeys(urls))
candidates = [u for u in urls if "preview" in u.lower()]
print(f"URLS total={len(urls)} preview_candidates={len(candidates)}", flush=True)

lines = []
for u in candidates:
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "WorkBuddy/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()
            if data[:8] != PNG_MAGIC:
                lines.append(f"NOT_PNG {u[:90]} head={data[:8]!r}")
                break
            p = HERE / "artifact_01.png"
            p.write_bytes(data)
            lines.append(f"DOWNLOADED {p.name} {len(data)} B "
                         f"sha256={hashlib.sha256(data).hexdigest()} attempt={attempt}")
            print(lines[-1], flush=True)
            break
        except Exception as exc:
            lines.append(f"ATTEMPT {attempt} {type(exc).__name__}: {exc}")
            print(lines[-1], flush=True)
    else:
        continue
    break

(HERE / "retry_preview.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("RETRY_DONE", flush=True)
