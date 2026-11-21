"""女角色 3D 核查的承重判据（答疑型交付，12 条）。

证的是「女角色 3D 确实存在且可见」，不是审美：
  · .blend 里只有女角色高模 + 驱动用代理壳，没有对手怪；
  · Godot 主场景真的把女角色摆进去了，代理壳在抓帧前已隐藏；
  · 两张对照图是引擎内真实截帧且确实是两个不同角色；
  · 全程对游戏工程、E 路线归档零污染。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
E = BAKE / "E路线-玩家3D绑骨"
D = BAKE / "D路线-CreativeReview与引擎截帧"
GAME = BAKE.parent / "牌拳-CardBoxer"
OUT = HERE / "verify_showcase_result.json"
CHECKS: list[dict] = []


def expect(name: str, cond: bool, detail: str) -> None:
    CHECKS.append({"name": name, "ok": bool(cond), "detail": str(detail)})


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def stddev(p: Path) -> float:
    try:
        im = Image.open(p).convert("RGB").resize(
            (128, 128), Image.Resampling.LANCZOS)
        return round(sum(ImageStat.Stat(im).stddev) / 3, 3)
    except Exception as exc:  # noqa: BLE001
        return -1.0


def lowfreq_mae(a: Path, b: Path) -> float:
    ims = []
    for p in (a, b):
        ims.append(Image.open(p).convert("RGB").resize(
            (24, 24), Image.Resampling.LANCZOS))
    return round(sum(ImageStat.Stat(
        ImageChops.difference(*ims)).mean) / 3, 4)


def main() -> int:
    try:
        inv = load(HERE / "scene_inventory.json")
        src = load(E / "source_probe.json")
        gd = load(HERE / "godot_player_result.json")
        boards = load(HERE / "showcase_boards.json")
        viewer = load(HERE / "viewer_manifest.json")
        baseline = load(E / "baseline_e.json")

        # S-01 .blend 场景里没有对手怪
        objs = inv["objects"]
        meshes = {o["name"]: o for o in objs if o["type"] == "MESH"}
        hi = meshes.get("node_0", {})
        shell = meshes.get("e_continuous_shell", {})
        foe_named = [o["name"] for o in objs
                     if "foe" in o["name"].lower()]
        expect("S-01_blend_contains_player_not_foe",
               len(meshes) == 2 and not foe_named
               and hi.get("verts") == 57901
               and hi.get("hide_render") is False
               and any(m["type"] == "SURFACE_DEFORM"
                       and m["is_bound"] for m in hi.get("modifiers", []))
               and shell.get("verts") == 14070
               and shell.get("hide_render") is True
               and any(o["type"] == "ARMATURE" for o in objs),
               f"meshes={sorted(meshes)} foe_named={foe_named} "
               f"hi_verts={hi.get('verts')}")

        # S-02 源 GLB 与贴图都是女角色 V4b
        v4b = Path(src["glb"]["path"])
        imgs = [i for i in inv["images"] if i["size"] == [4096, 4096]
                and i["packed"]]
        expect("S-02_source_glb_is_v4b_player",
               v4b.is_file() and sha256(v4b) == src["glb"]["sha256"]
               == baseline["singles"]["v4b_glb"]["sha256"]
               and len(imgs) == 3
               and inv["camera"] == "e_cam",
               f"glb_sha={src['glb']['sha256'][:12]} packed4096="
               f"{len(imgs)} camera={inv['camera']}")

        # S-03 打开即所见 == 隐藏代理壳口径
        a, b = HERE / "A-打开即所见.png", HERE / "B-隐藏代理壳.png"
        expect("S-03_open_as_is_matches_delivery_view",
               a.is_file() and b.is_file()
               and a.stat().st_size > 10000 and b.stat().st_size > 10000
               and abs(a.stat().st_size - b.stat().st_size) <= 100
               and Image.open(a).size == Image.open(b).size == (768, 768),
               f"A={a.stat().st_size} B={b.stat().st_size} "
               f"delta={abs(a.stat().st_size - b.stat().st_size)}")

        # S-04 Godot 主场景接线
        pg = (HERE / "probe_project_player" / "project.godot").read_text(
            encoding="utf-8")
        tscn = (HERE / "probe_project_player" / "scenes" /
                "player_showcase.tscn").read_text(encoding="utf-8")
        show = (HERE / "probe_project_player" / "scenes" /
                "showcase.gd").read_text(encoding="utf-8")
        expect("S-04_godot_main_scene_wired",
               'run/main_scene="res://scenes/player_showcase.tscn"' in pg
               and 'res://assets/player-full.glb' in tscn
               and 'res://scenes/showcase.gd' in tscn
               and '"e_continuous_shell"' in show
               and "visible = false" in show
               and "Camera3D" in tscn,
               f"main_scene={'player_showcase.tscn' in pg} "
               f"hide_shell={'visible = false' in show}")

        # S-05 引擎内渲染结果
        expect("S-05_godot_render_clean",
               gd["ok"] is True
               and gd["copy_identical"] is True
               and gd["editor_import"]["returncode"] == 0
               and gd["editor_import"]["import_file"] is True
               and gd["render"]["returncode"] == 0
               and gd["render"]["has_opengl"] is True
               and gd["render"]["script_errors"] == 0
               and gd["render"]["headless"] is False
               and len(gd["pngs"]) == 4
               and sha256(HERE / "probe_project_player" / "assets" /
                          "player-full.glb") == gd["source_glb_sha256"],
               f"ok={gd['ok']} views={len(gd['pngs'])} "
               f"gl={gd['render']['has_opengl']} "
               f"errs={gd['render']['script_errors']}")

        # S-06 代理壳可见性：初始化 / _ready / 抓帧前三处对账
        sc = gd["scene"]
        expect("S-06_proxy_shell_hidden_before_capture",
               sc["init_before_ready"]["hidden_proxy_shell"] == 0
               and sc["after_ready"]["hidden_proxy_shell"] == 1
               and sc["at_capture"]["hidden_proxy_shell"] == 1
               and sc["at_capture"]["visible_highpoly"] == 1
               and sc["hidden_proxy_shell"] == 1
               and sc["visible_highpoly"] == 1
               and sc["ready_ok"] is True,
               f"init={sc['init_before_ready']} "
               f"ready={sc['after_ready']} capture={sc['at_capture']}")

        # S-07 四张截帧
        pngs = gd["pngs"]
        paths = [Path(x["path"]) for x in pngs]
        digests = [sha256(p) for p in paths]
        expect("S-07_four_godot_shots_valid",
               all(x["exists"] and x["bytes"] > 20000
                   and x["save_error"] == 0
                   and x["w"] == 900 and x["h"] == 1100 for x in pngs)
               and len(set(digests)) == 4
               and all(stddev(p) > 8 for p in paths),
               f"shots={len(pngs)} distinct={len(set(digests))} "
               f"stddev_min={min(stddev(p) for p in paths)}")

        # S-08 两张板
        bl = boards["boards"]
        bpaths = [HERE / "boards" / x["file"] for x in bl]
        bsha = [sha256(p) for p in bpaths]
        expect("S-08_two_boards_valid",
               len(bl) == 2
               and all(p.is_file()
                       and p.stat().st_size == x["bytes"]
                       and Image.open(p).size == (x["w"], x["h"])
                       for p, x in zip(bpaths, bl))
               and len(set(bsha)) == 2
               and all(stddev(p) > 8 for p in bpaths)
               and boards["hidden_proxy_shell"] == 1,
               f"boards={len(bl)} distinct={len(set(bsha))}")

        # S-09 左右确实是两个不同角色（不是同一张复制）
        mae = lowfreq_mae(HERE / "shots" / "godot-player-front.png",
                          D / "shots" / "godot-front.png")
        expect("S-09_player_and_foe_are_distinct",
               mae > 15.0
               and (D / "shots" / "godot-front.png").is_file(),
               f"lowfreq_mae_24x24={mae} threshold=15.0")

        # S-10 离线查看器
        page = (HERE / "女角色3D查看器.html").read_text(encoding="utf-8")
        srcs = re.findall(r'data-src="([^"]+)"', page)
        expect("S-10_offline_viewer_complete",
               len(viewer["items"]) == 12 and len(srcs) == 12
               and viewer["offline"] is True
               and all((HERE / s).is_file() for s in srcs)
               and "http://" not in page and "https://" not in page,
               f"items={len(viewer['items'])} srcs={len(srcs)} "
               f"missing={sum(not (HERE/s).is_file() for s in srcs)}")

        # S-11 零污染
        drift = []
        for rel, meta in baseline["game"].items():
            p = GAME / rel
            if not p.is_file() or p.stat().st_size != meta["bytes"] \
                    or sha256(p) != meta["sha256"]:
                drift.append(rel)
        for key, meta in baseline["singles"].items():
            p = Path(meta["path"])
            if not p.is_file() or p.stat().st_size != meta["bytes"] \
                    or sha256(p) != meta["sha256"]:
                drift.append("single:" + key)
        exts = ("*.glb", "*.gltf", "*.obj", "*.fbx", "*.blend",
                "*.dae", "*.vrm")
        game3d = [p for e in exts for p in GAME.rglob(e)]
        ev = load(E / "verify_e_result.json")
        elist = (E / "文件清单.txt").read_text(encoding="utf-8")
        e_entries = sum(1 for l in elist.splitlines()
                        if l.startswith("WORK/"))
        expect("S-11_game_and_e_route_zero_drift",
               not drift and not game3d
               and ev["passed"] == ev["total"] == 26 and not ev["failed"]
               and e_entries == 80 and "条目数由脚本现算：80" in elist,
               f"drift={len(drift)} game3d={len(game3d)} "
               f"verify_e={ev['passed']}/{ev['total']} "
               f"e_entries={e_entries}")

        # S-12 渲染日志三处可见性标记齐全
        log = (HERE / "logs" / "godot_render_player.log").read_text(
            encoding="utf-8", errors="replace")
        expect("S-12_render_log_markers",
               "SCENE_LOADED " in log and "SHOWCASE_READY " in log
               and "FRAME_VISIBILITY " in log
               and "RENDER_JSON " in log
               and "SCRIPT ERROR" not in log,
               f"markers=4 script_errors={log.count('SCRIPT ERROR')}")
    except Exception as exc:  # noqa: BLE001
        expect("S-00_inputs_parseable", False, repr(exc))

    passed = sum(1 for c in CHECKS if c["ok"])
    failed = [c["name"] for c in CHECKS if not c["ok"]]
    OUT.write_text(json.dumps(
        {"total": len(CHECKS), "passed": passed, "failed": failed,
         "checks": CHECKS}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for c in CHECKS:
        print(f"{'OK ' if c['ok'] else 'RED'} {c['name']:<42} "
              f"{c['detail']}")
    ok = passed == len(CHECKS) == 12 and not failed
    print(f"VERIFY_SHOWCASE {passed}/{len(CHECKS)} failed={failed}")
    print("SHOWCASE_VERIFIED" if ok else "SHOWCASE_VERIFY_FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
