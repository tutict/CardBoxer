"""V3 / V4 / V4b 造型探针的承重判据。

只证明：prompt 合规、产物按魔数分类正确、模型仍是静态单 mesh、
三版渲染确实用了同一套相机、脸模与上半身特写确实不是同一张图、
游戏源码零改动。**一条都不评「好看」**，好看只能靠看图。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
V3 = BAKE / "3d-model-probe-v3"
V4B = BAKE / "3d-model-probe-v4b"
GAME = BAKE.parent / "CardBoxer"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def diff_px(a: Path, b: Path, tol=8) -> int:
    with Image.open(a) as x, Image.open(b) as y:
        d = ImageChops.difference(x.convert("RGB"), y.convert("RGB")).convert("L")
    return d.point(lambda v: 255 if v > tol else 0).histogram()[255]


def nonblank(p: Path) -> int:
    with Image.open(p) as f:
        im = f.convert("RGB").resize((160, 160), Image.Resampling.BILINEAR)
    return len(set(im.getdata()))


def main():
    checks = []

    def ck(name, ok, detail=""):
        checks.append((name, bool(ok), detail))

    # 1 prompt 合规（长度 / 禁词 / 约束 / 哈希自洽）
    for tag, d in (("V4", HERE), ("V4b", V4B)):
        cp = jload(d / "check_prompt.json")
        # 与 check_prompt.py 完全同口径：strip() 后再编码。
        # 直接对文件字节算 sha 会多算末尾换行，两套数字打架不是产物坏。
        prompt_sha = hashlib.sha256(
            (d / "prompt.txt").read_text(encoding="utf-8").strip().encode()).hexdigest()
        ck(f"{tag}_prompt_ok",
           cp["verdict"] == "PROMPT_OK"
           and cp["length"] <= 1024
           and cp["sha256"] == prompt_sha
           and not cp["forbidden_hits"],
           f"len={cp['length']} sha={prompt_sha[:12]}")

    # 2 产物按魔数分类；GLB 结构仍是静态单 mesh
    for tag, d in (("V4", HERE), ("V4b", V4B)):
        sigs = {}
        for p in sorted(d.glob("artifact_*")):
            if not p.is_file():
                continue
            h = p.read_bytes()[:8]
            k = ("glb" if h[:4] == b"glTF" else "png" if h[:8] == b"\x89PNG\r\n\x1a\n"
                 else "zip" if h[:2] == b"PK" else "fbx" if b"Kaydara" in p.read_bytes()[:64]
                 else "unknown")
            sigs.setdefault(k, []).append(p)
        ck(f"{tag}_four_artifacts_by_magic",
           all(k in sigs and len(sigs[k]) == 1 for k in ("glb", "png", "zip", "fbx")),
           str({k: [p.name for p in v] for k, v in sigs.items()}))

        ins = jload(d / "model_inspection.json")
        c = ins["counts"]
        ck(f"{tag}_still_static_single_mesh",
           c["skins"] == 0 and c["animations"] == 0 and c["meshes"] == 1
           and c["images"] == 3 and ins["vertices_total"] > 30000
           and ins["connected_shells_unionfind"] > 0
           and not ins["has_skin"] and not ins["has_animation"],
           f"verts={ins['vertices_total']} shells={ins['connected_shells_unionfind']} "
           f"skins={c['skins']} anim={c['animations']}")

        rep = jload(d / "probe_report.json")
        got = {a["file"]: sha(d / a["file"]) for a in rep["artifacts"]}
        ck(f"{tag}_probe_report_sha_matches",
           all(got[a["file"]] == a["sha256"] for a in rep["artifacts"]),
           f"{len(got)} artifacts")

    # 3 承重判据：三版用的是同一套相机 / 灯光 / 材质策略
    specs = {}
    for tag, d in (("v3", HERE), ("v4", HERE), ("v4b", V4B)):
        r = jload(d / f"render_{tag}.json")
        specs[tag] = [(s["shot"], s["angle_deg"], s["target_z"],
                       s["ortho_scale"], s["resolution"]) for s in r["shots"]]
    same = specs["v3"] == specs["v4"] == specs["v4b"]
    ck("three_versions_share_identical_cameras", same,
       f"shots={len(specs['v3'])} v3==v4==v4b={same}")
    policies = [jload(d / f"render_{t}.json")["material_policy"]
                for t, d in (("v3", HERE), ("v4", HERE), ("v4b", V4B))]
    ck("material_policy_identical", len(set(policies)) == 1, policies[0][:60])

    # 4 每张渲染图存在、尺寸对、非空白
    expect = {s[0]: s[4] for s in specs["v3"]}
    for tag, d in (("v3", HERE), ("v4", HERE), ("v4b", V4B)):
        ok, detail = True, {}
        for name, res in expect.items():
            p = d / f"{tag}-{name}.png"
            if not p.is_file():
                ok = False
                detail[name] = "MISSING"
                continue
            with Image.open(p) as f:
                size = f.size
            n = nonblank(p)
            detail[name] = f"{size} colors={n}"
            ok &= size == (res, res) and n > 300
        ck(f"{tag}_seven_renders_valid", ok, str(detail))

    # 5 脸模 / 上半身特写确实换过模型，不是把同一张图复制三份
    face = [HERE / "v3-face-front.png", HERE / "v4-face-front.png", V4B / "v4b-face-front.png"]
    upper = [HERE / "v3-upper.png", HERE / "v4-upper.png", V4B / "v4b-upper.png"]
    for label, trio, floor in (("face", face, 30000), ("upper", upper, 50000)):
        pairs = [(0, 1), (1, 2), (0, 2)]
        vals = [diff_px(trio[i], trio[j]) for i, j in pairs]
        ck(f"{label}_closeups_are_distinct", all(v > floor for v in vals), str(vals))

    # 6 对照板齐备
    boards = [HERE / "V3-V4-model-comparison.png", HERE / "V3-V4-face-detail.png",
              V4B / "V3-V4-V4b-three-version-comparison.png"]
    ck("comparison_boards_exist",
       all(p.is_file() and nonblank(p) > 300 for p in boards),
       str([p.name for p in boards]))

    # 7 游戏源码零改动
    marker = (HERE / "V4-model-spec.txt").stat().st_mtime
    newer = [str(p.relative_to(GAME)) for p in GAME.rglob("*")
             if p.is_file() and ".godot" not in p.parts and p.stat().st_mtime > marker]
    ck("game_sources_not_modified", not newer, f"newer={newer[:6]}")

    passed = sum(1 for _, ok, _ in checks if ok)
    lines = [f"{'PASS' if ok else 'FAIL'}  {n}  {d}" for n, ok, d in checks]
    verdict = "MODEL_V4_VERIFIED" if passed == len(checks) else "MODEL_V4_CHECK_FAILED"
    text = "\n".join(lines) + f"\n\n{passed}/{len(checks)} PASS  {verdict}\n"
    (HERE / "verify_v4.log").write_text(text, encoding="utf-8")
    (V4B / "verify_v4.log").write_text(text, encoding="utf-8")
    (HERE / "verify_v4_result.json").write_text(
        json.dumps({"verdict": verdict, "passed": passed, "total": len(checks),
                    "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(text)
    raise SystemExit(0 if passed == len(checks) else 1)


if __name__ == "__main__":
    main()
