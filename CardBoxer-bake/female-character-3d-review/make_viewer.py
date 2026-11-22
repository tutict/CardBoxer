"""生成完全离线的女角色 3D 查看器：把多处女角色资产集中到一个页面。

只复制已有 PNG，不重渲、不改任何既有资产；生成时逐个自检 img src 存在。
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
E = BAKE / "route-e-player-3d-rigging"
V4B = BAKE / "3d-model-probe-v4b"
ASSETS = HERE / "viewer_assets"
ASSETS.mkdir(exist_ok=True)
OUT = HERE / "female-character-3D-viewer.html"

ITEMS = [
    ("Godot 正面 0°", HERE / "shots" / "godot-player-front.png",
     "godot-front.png", "Godot 4.5 引擎内 · player-full.glb"),
    ("Godot 斜 35°", HERE / "shots" / "godot-player-angle35.png",
     "godot-angle35.png", "Godot 4.5 引擎内 · 同一套固定灯光"),
    ("Godot 侧 90°", HERE / "shots" / "godot-player-side90.png",
     "godot-side90.png", "侧面厚度可读，无薄壳退化"),
    ("Godot 背 180°", HERE / "shots" / "godot-player-back.png",
     "godot-back.png", "背面长发与披风"),
    ("blend 打开即所见", HERE / "A-initial-view.png",
     "blend-open.png", "player-V4b-deformable-continuous-shell.blend 双击打开所见"),
    ("E 站架 x1.5", E / "frames" / "e-stance-x15.png",
     "e-stance.png", "SURFACE_DEFORM 绑定后 rest"),
    ("E jab #6", E / "frames" / "e-jab07-x15.png",
     "e-jab.png", "13 骨逐帧驱动 · 单侧前臂"),
    ("E cross #10", E / "frames" / "e-cross11-x15.png",
     "e-cross.png", "13 骨逐帧驱动 · 后手"),
    ("E wave #17", E / "frames" / "e-wave18-x15.png",
     "e-wave.png", "13 骨逐帧驱动 · 双手"),
    ("E 55° 侧视", E / "frames" / "e-stance-angle55.png",
     "e-angle55.png", "Blender 侧视体积"),
    ("V4b 源正面", V4B / "v4b-front.png",
     "v4b-front.png", "生成模型原始四视角"),
    ("V4b 脸模特写", V4B / "v4b-face-front.png",
     "v4b-face.png", "琥珀分层虹膜 / 发饰"),
]

rows = []
for label, src, name, note in ITEMS:
    if not src.is_file():
        raise SystemExit(f"MISSING SOURCE: {src}")
    dst = ASSETS / name
    shutil.copyfile(src, dst)
    rows.append((label, name, note, dst.stat().st_size))

buttons = "\n".join(
    f'<button class="v" data-src="viewer_assets/{html.escape(name)}" '
    f'data-note="{html.escape(note)}" data-label="{html.escape(label)}">'
    f'{html.escape(label)}</button>'
    for label, name, note, _ in rows)

doc = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>女角色 V4b 3D 查看器</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; background:#121824; color:#ecf0fa;
         font-family:"Microsoft YaHei",system-ui,sans-serif; }
  header { padding:20px 28px 14px; border-bottom:1px solid #26304a; }
  h1 { margin:0; font-size:22px; }
  header p { margin:8px 0 0; color:#98a4b8; font-size:14px; }
  main { display:flex; gap:24px; padding:24px 28px; align-items:flex-start; }
  nav { width:210px; display:flex; flex-direction:column; gap:7px;
        flex:none; }
  button.v { text-align:left; padding:9px 12px; border-radius:8px;
             border:1px solid #2b3550; background:#1e2636; color:#c8d2e4;
             cursor:pointer; font-size:14px; font-family:inherit; }
  button.v:hover { border-color:#f0d6a0; }
  button.v.on { background:#3a3320; border-color:#f0d6a0; color:#f0d6a0; }
  figure { margin:0; flex:1; min-width:0; }
  .stage { background:#1e2636; border:1px solid #2b3550; border-radius:10px;
           min-height:640px; display:flex; align-items:center;
           justify-content:center; overflow:hidden; }
  img { max-width:100%; max-height:76vh; object-fit:contain; display:block; }
  figcaption { margin-top:12px; color:#98a4b8; font-size:14px; }
  .meta { margin-top:16px; font-size:13px; color:#7e8ea8; line-height:1.7; }
</style>
</head>
<body>
<header>
  <h1>女角色 V4b · 3D 资产查看器</h1>
  <p>全部为真实渲染图，离线可看。左列切换；Godot 四视角是引擎内截帧，
     E 路线帧是 Blender 13 骨逐帧驱动。</p>
</header>
<main>
  <nav id="nav">
__BUTTONS__
  </nav>
  <figure>
    <div class="stage"><img id="pic" alt="女角色 3D" src=""></div>
    <figcaption id="cap"></figcaption>
    <div class="meta">
      静态资产说明：player-full.glb 是 1 skin / 14 joints / 0 animations，
      高模无 JOINTS_0；能驱动的是 Blender 端的
      player-V4b-deformable-continuous-shell.blend，Godot 内目前只能看静态 A-pose。<br>
      可运行游戏工程里玩家战斗层仍是 2D 代码自绘，3D 资产没有进游戏。
    </div>
  </figure>
</main>
<script>
  const pic = document.getElementById('pic');
  const cap = document.getElementById('cap');
  const btns = Array.from(document.querySelectorAll('button.v'));
  function show(b) {
    btns.forEach(x => x.classList.toggle('on', x === b));
    pic.src = b.dataset.src;
    cap.textContent = b.dataset.label + '  ·  ' + b.dataset.note;
  }
  btns.forEach(b => b.addEventListener('click', () => show(b)));
  show(btns[0]);
</script>
</body>
</html>
""".replace("__BUTTONS__", buttons)
OUT.write_text(doc, encoding="utf-8")

# 生成时逐个自检：HTML 里出现的每个 img src 都在磁盘上。
missing = [name for _, name, _, _ in rows
           if not (ASSETS / name).is_file()]
if missing:
    raise SystemExit(f"MISSING VIEWER ASSETS: {missing}")
(HERE / "viewer_manifest.json").write_text(
    json.dumps({"items": [{"label": l, "file": n, "note": note,
                           "bytes": b} for l, n, note, b in rows],
                "html": OUT.name, "offline": True},
               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"VIEWER_ITEMS={len(rows)} HTML_BYTES={OUT.stat().st_size} "
      f"ASSETS_MISSING={len(missing)}")
print("VIEWER_OK")
