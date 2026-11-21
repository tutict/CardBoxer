"""生成完全离线的 V4b 建模查看页：七视角切换 + 两张对照图。

不依赖 CDN、不用 fetch、不加载 GLB —— 图片全部是同目录相对路径，
file:// 直接打开也能用。视角参数与结构统计从 V4b 的 JSON 读，可复算。
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
V4B = HERE.parent / "3D模型探针V4b"
RENDER = json.loads((V4B / "render_v4b.json").read_text(encoding="utf-8"))
INSPECT = json.loads((V4B / "model_inspection.json").read_text(encoding="utf-8"))

LABELS = {
    "front": "正面 0°", "angle25": "斜视 25°", "angle55": "侧视 55°",
    "back35": "背面 35°", "face-front": "脸部正面", "face-25": "脸部 25°",
    "upper": "上半身特写",
}

items = []
for s in RENDER["shots"]:
    items.append({
        "file": s["file"],
        "label": LABELS[s["shot"]],
        "detail": f"{s['resolution']}² · angle {s['angle_deg']}° · "
                  f"ortho {s['ortho_scale']} · target_z {s['target_z']}",
        "group": "同相机渲染",
    })
items.append({
    "file": "artifact_01.png", "label": "服务预览原图",
    "detail": "工程师选定的那张 PBR 预览（白底 512²）", "group": "对照",
})
items.append({
    "file": "V3-V4-V4b-三版对照.png", "label": "V3 / V4 / V4b 对照",
    "detail": "三版演进：脸模、长袖、黑襟片、头饰弱化", "group": "对照",
})

c = INSPECT["counts"]
struct = (f"{INSPECT['vertices_total']:,} 顶点 / {INSPECT['triangles_total']:,} 三角 / "
          f"{c['textures']} 张内嵌 PBR / {c['skins']} skins / {c['animations']} animations / "
          f"{INSPECT['connected_shells_unionfind']:,} 连通壳 · 自动绑骨 0 覆盖")

TEMPLATE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>《牌拳》V4b 定稿造型 · 建模查看器</title>
<style>
:root{--bg:#14161c;--panel:#20242e;--card:#30343e;--edge:#565e70;
      --cyan:#46d2e6;--fg:#eef0f6;--muted:#96a0b4}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
     font-family:system-ui,"Microsoft YaHei","PingFang SC",sans-serif}
header{padding:18px 28px 12px;border-bottom:1px solid var(--edge)}
h1{margin:0;font-size:21px;letter-spacing:.5px}
.sub{margin-top:6px;font-size:13px;color:var(--muted)}
nav{display:flex;flex-wrap:wrap;gap:8px;padding:14px 28px 6px}
button{background:var(--panel);color:var(--fg);border:1px solid var(--edge);
       border-radius:7px;padding:8px 14px;font-size:13px;cursor:pointer;
       font-family:inherit;transition:.15s}
button:hover{border-color:var(--cyan)}
button.on{background:var(--cyan);color:#101820;border-color:var(--cyan);font-weight:700}
.sep{width:100%;height:0}
main{display:flex;gap:18px;padding:8px 28px 20px;align-items:flex-start;flex-wrap:wrap}
.stage{flex:1 1 620px;min-width:320px;background:var(--card);border:1px solid var(--edge);
       border-radius:12px;display:flex;align-items:center;justify-content:center;
       height:min(74vh,780px);overflow:hidden}
.stage img{max-width:100%;max-height:100%;object-fit:contain;display:block}
aside{flex:0 1 300px;min-width:250px;background:var(--panel);border:1px solid var(--edge);
      border-radius:12px;padding:18px}
.kicker{color:var(--cyan);font-size:12px;letter-spacing:1px;text-transform:uppercase}
h2{margin:8px 0 12px;font-size:18px}
.meta{font-size:13px;color:var(--muted);line-height:1.8}
.meta b{color:var(--fg);font-weight:600}
hr{border:0;border-top:1px solid var(--edge);margin:16px 0}
.note{font-size:12px;color:var(--muted);line-height:1.8}
footer{padding:12px 28px 26px;font-size:12px;color:var(--muted);border-top:1px solid var(--edge)}
kbd{background:var(--panel);border:1px solid var(--edge);border-radius:4px;padding:1px 6px}
</style>
</head>
<body>
<header>
  <h1>《牌拳》V4b 定稿造型 · 建模查看器</h1>
  <div class="sub">Blender 5.2.3 · 7-shot 同相机正交渲染 · 保留 PBR 原材质 · 离线渲染，非游戏内实渲</div>
</header>
<nav id="tabs"></nav>
<main>
  <div class="stage"><img id="view" alt="V4b 建模渲染"></div>
  <aside>
    <div class="kicker">当前视角</div>
    <h2 id="label"></h2>
    <div class="meta" id="detail"></div>
    <hr>
    <div class="kicker">结构实测</div>
    <div class="note" id="struct"></div>
    <hr>
    <div class="note">切换：<kbd>←</kbd> <kbd>→</kbd> 或数字键 <kbd>1</kbd>–<kbd>9</kbd>。<br>
    图片均为本目录相对路径，完全离线，不加载 GLB / 不依赖 CDN。</div>
  </aside>
</main>
<footer id="foot"></footer>
<script>
const SHOTS = __SHOTS__;
const STRUCT = __STRUCT__;
let i = 0;
const tabs = document.getElementById('tabs');
const view = document.getElementById('view');
const label = document.getElementById('label');
const detail = document.getElementById('detail');
document.getElementById('struct').textContent = STRUCT;
SHOTS.forEach((s, n) => {
  if (n > 0 && s.group !== SHOTS[n-1].group) {
    const sep = document.createElement('div'); sep.className = 'sep'; tabs.appendChild(sep);
  }
  const b = document.createElement('button');
  b.textContent = (n+1) + ' · ' + s.label;
  b.onclick = () => show(n);
  tabs.appendChild(b);
});
function show(n){
  i = (n + SHOTS.length) % SHOTS.length;
  const s = SHOTS[i];
  view.src = s.file;
  label.textContent = s.label;
  detail.innerHTML = '<b>' + s.file + '</b><br>' + s.detail + '<br>分组：' + s.group;
  [...tabs.querySelectorAll('button')].forEach((b,k) => b.classList.toggle('on', k === i));
  document.getElementById('foot').textContent =
    '共 ' + SHOTS.length + ' 张 · 第 ' + (i+1) + ' 张 · 素材来自 3D模型探针V4b/（原图逐字节复制）';
}
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowRight') show(i+1);
  else if (e.key === 'ArrowLeft') show(i-1);
  else if (/^[1-9]$/.test(e.key)) show(Number(e.key)-1);
});
show(0);
</script>
</body>
</html>
"""

# 每个 img src 都必须是本目录里真实存在的文件，否则页面会静默空白
missing = [s["file"] for s in items if not (HERE / s["file"]).is_file()]
if missing:
    raise SystemExit(f"VIEWER_MISSING_ASSETS {missing}")

html = (TEMPLATE
        .replace("__SHOTS__", json.dumps(items, ensure_ascii=False))
        .replace("__STRUCT__", json.dumps(struct, ensure_ascii=False)))
out = HERE / "V4b-建模查看器.html"
out.write_text(html, encoding="utf-8")
print(json.dumps({"output": out.name, "bytes": out.stat().st_size,
                  "shots": len(items), "missing_assets": missing}, ensure_ascii=False))
print("VIEWER_OK")
