"""变异验证：故意改坏 V4/V4b 产物，确认 verify_v4.py 的关键判据会红。

纪律：逐字节备份 / 还原，sha256 证明；每条点名一条应保持绿色的哨兵判据；
跑完 clean re-run 必须 17/17 才记 MUTATION_OK。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
V4B = HERE.parent / "3D模型探针V4b"
VERIFY = HERE / "verify_v4.py"
RESULT = HERE / "verify_v4_result.json"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run_verify() -> dict:
    subprocess.run([sys.executable, str(VERIFY)], capture_output=True, text=True)
    return json.loads(RESULT.read_text(encoding="utf-8"))


def status(res, name):
    return next(c["ok"] for c in res["checks"] if c["name"] == name)


def mutate_camera(p: Path):
    d = json.loads(p.read_text(encoding="utf-8"))
    d["shots"][0]["target_z"] = 9.99
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def mutate_inspection(p: Path):
    d = json.loads(p.read_text(encoding="utf-8"))
    d["counts"]["skins"] = 1
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


CASES = [
    {
        "id": "M1", "desc": "render_v4.json 的相机 target_z 被改（同相机判据失效）",
        "file": HERE / "render_v4.json", "mutate": mutate_camera,
        "expect_red": "three_versions_share_identical_cameras",
        "sentinel": "v4_seven_renders_valid",
    },
    {
        "id": "M2", "desc": "V4b 脸特写被换成 V3 的副本（三版不是不同模型）",
        "file": V4B / "v4b-face-front.png",
        "mutate": lambda p: p.write_bytes((HERE / "v3-face-front.png").read_bytes()),
        "expect_red": "face_closeups_are_distinct",
        "sentinel": "v4b_seven_renders_valid",
    },
    {
        "id": "M3", "desc": "V4b model_inspection.json 的 skins 改成 1（假装能绑骨）",
        "file": V4B / "model_inspection.json", "mutate": mutate_inspection,
        "expect_red": "V4b_still_static_single_mesh",
        "sentinel": "V4b_probe_report_sha_matches",
    },
]


def main():
    rows = []
    for c in CASES:
        target = c["file"]
        original = target.read_bytes()
        original_sha = sha(target)
        try:
            c["mutate"](target)
            res = run_verify()
            red = not status(res, c["expect_red"])
            green = status(res, c["sentinel"])
            rows.append({
                "id": c["id"], "desc": c["desc"],
                "verdict": "CAUGHT" if red and green else "MISSED",
                "target_red": c["expect_red"], "target_was_red": red,
                "sentinel": c["sentinel"], "sentinel_was_green": green,
                "passed": res["passed"],
            })
        finally:
            target.write_bytes(original)
        restored = sha(target) == original_sha
        rows[-1]["restored_sha_ok"] = restored
        if not restored:
            rows[-1]["verdict"] = "RESTORE_FAILED"
        r = rows[-1]
        print(f"{c['id']} {r['verdict']} red={red} green={green} restore={restored}")

    clean = run_verify()
    clean_ok = clean["verdict"] == "MODEL_V4_VERIFIED" and clean["passed"] == clean["total"]
    caught = sum(1 for r in rows if r["verdict"] == "CAUGHT")
    ok = caught == len(rows) and clean_ok
    out = {"cases": rows, "caught": caught, "total": len(rows),
           "clean_rerun": clean_ok, "clean_passed": clean["passed"],
           "verdict": "MUTATION_OK" if ok else "MUTATION_FAILED"}
    (HERE / "mutation_v4_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (HERE / "mutation_v4.log").write_text(
        "\n".join(f"{r['id']} {r['verdict']}  {r['desc']}  "
                  f"red={r['target_was_red']} sentinel_green={r['sentinel_was_green']} "
                  f"restore={r['restored_sha_ok']}" for r in rows)
        + f"\n\n{caught}/{len(rows)} CAUGHT  clean_rerun={clean['passed']}/{clean['total']}\n",
        encoding="utf-8")
    print(json.dumps({"caught": caught, "clean": clean["passed"], "verdict": out["verdict"]}))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
