"""双侧独立建模 · 12 条判据的变异验证。

纪律（沿用 B 路线 / World3D 轮）：
  - 只改「被测输入」（SubViewport 原图、单层真值），不改守卫脚本自身；
  - 守卫必须 rc=1 且打印 CHECK ... False；崩栈/无 FAIL 行一律不算 CAUGHT；
  - 锚点（目标存在、payload 生效、命中数=1）不成立判 DID NOT RUN，计入未证明；
  - 每个变异二进制写回 + sha256 证明还原；
  - 收尾 clean re-run 必须 12/12 全绿，且三份产物 sha 与变异前基线一致；
  - --selftest-dnr 注入一个「目标文件不存在」的假用例，证明 DNR 分支有牙。

用法：python mutation_separate_models.py
      python mutation_separate_models.py --selftest-dnr
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BAKE = HERE.parent
TRUTH = BAKE / "route-b-asset-deduplication" / "data" / "single_layers.json"
SHOTS = HERE / "shots"
TARGET = HERE / "make_separate_models.py"
REPORT = HERE / "data" / "separate_models.json"
PRODUCTS = [
    HERE / "boards" / "independent-models-presentation-board.png",
    HERE / "boards" / "independent-models-cross-talk-comparison.png",
    REPORT,
]
OUT = HERE / "data" / "mutation_separate_models.json"
LOGDIR = HERE / "logs" / "mutations_separate"

SP = SHOTS / "shipped" / "sh-shipped-sv-player.png"
SF = SHOTS / "shipped" / "sh-shipped-sv-foe.png"
LP = SHOTS / "legacy" / "sh-legacy-sv-player.png"
LF = SHOTS / "legacy" / "sh-legacy-sv-foe.png"
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4"
    "z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==")

CASES = [
    {"id": "M1", "desc": "玩家视口换成共享 World3D 串扰图（模拟修复回归）",
     "target": SP, "kind": "copy", "src": LP},
    {"id": "M2", "desc": "对手视口换成共享 World3D 串扰图（模拟修复回归）",
     "target": SF, "kind": "copy", "src": LF},
    {"id": "M3", "desc": "单层真值 player sha 被篡改（防止拿错真值当证据）",
     "target": TRUTH, "kind": "sha_flip"},
    {"id": "M4", "desc": "改前对照组被换成干净图（防止上下排无差别）",
     "target": LF, "kind": "copy", "src": SF},
    {"id": "M5", "desc": "对手视口换成 1x1 空图（防止「文件存在」真空通过）",
     "target": SF, "kind": "bytes", "data": TINY_PNG},
]


def sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else ""


def payload_bytes(case: dict) -> tuple[bytes, int]:
    """返回 (变异字节, 锚点命中数)。命中数 != 1 一律判 DID NOT RUN。"""
    kind = case["kind"]
    if kind == "copy":
        p = case["src"]
        return (p.read_bytes(), 1) if p.is_file() else (b"", 0)
    if kind == "bytes":
        return case["data"], 1
    if kind == "sha_flip":
        if not (TRUTH.is_file() and REPORT.is_file()):
            return b"", 0
        whole = json.loads(REPORT.read_text(
            encoding="utf-8"))["single_layer_truth_sha256"]["player"]
        t = TRUTH.read_text(encoding="utf-8")
        hits = t.count(whole) if whole else 0
        if hits != 1:
            return b"", hits
        flipped = ("0" if whole[0] != "0" else "1") + whole[1:]
        return t.replace(whole, flipped).encode("utf-8"), 1
    return b"", 0


def run_target() -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run(
        [sys.executable, "-u", str(TARGET)], cwd=str(HERE),
        env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace")


def red_checks(out: str) -> list[str]:
    return [ln.split()[1] for ln in out.splitlines()
            if ln.startswith("CHECK ") and ln.strip().endswith("False")
            and len(ln.split()) >= 3]


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    selftest = "--selftest-dnr" in sys.argv
    cases = list(CASES)
    if selftest:
        cases.append({
            "id": "DNR-PROBE", "desc": "锚点目标不存在必须判 DID NOT RUN",
            "target": SHOTS / "__missing__.png", "kind": "copy", "src": SP})
    baseline = {p.as_posix(): sha_file(p) for p in PRODUCTS}

    rows: list[dict] = []
    for case in cases:
        t = case["target"]
        raw = t.read_bytes() if t.is_file() else b""
        raw_sha = hashlib.sha256(raw).hexdigest() if raw else ""
        payload, hits = payload_bytes(case)
        row = {"id": case["id"], "desc": case["desc"],
               "target": str(t), "original_sha256": raw_sha,
               "anchor_hits": hits}
        reason = ""
        status = "DID NOT RUN"
        if not t.is_file():
            reason = "target missing"
        elif hits != 1:
            reason = f"anchor hits={hits}"
        elif payload == raw:
            reason = "payload identical to original"
        else:
            t.write_bytes(payload)
            if sha_file(t) == raw_sha:
                reason = "mutation bytes not applied"
            else:
                proc = run_target()
                out = (proc.stdout or "") + (proc.stderr or "")
                (LOGDIR / f"{case['id']}.log").write_text(
                    out, encoding="utf-8")
                reds = red_checks(out)
                crashed = "Traceback" in out
                good = (proc.returncode == 1 and bool(reds)
                        and not crashed
                        and "SEPARATE_MODELS_FAILED" in out)
                status = "CAUGHT" if good else "MISSED"
                reason = ("rc=1 + FAIL 行" if good else
                          f"rc={proc.returncode} reds={len(reds)} "
                          f"crashed={crashed}")
                row.update({"returncode": proc.returncode,
                            "crashed": crashed, "red_checks": reds})
            t.write_bytes(raw)
            row["restored"] = sha_file(t) == raw_sha
        row.setdefault("restored", (not t.is_file() and not raw)
                       or (t.is_file() and sha_file(t) == raw_sha))
        row["status"] = status
        row["reason"] = reason
        rows.append(row)

    clean = run_target()
    clean_out = (clean.stdout or "") + (clean.stderr or "")
    (LOGDIR / "clean.log").write_text(clean_out, encoding="utf-8")
    clean_green = (clean.returncode == 0
                   and "SEPARATE_MODELS_OK" in clean_out
                   and not red_checks(clean_out))
    after = {p.as_posix(): sha_file(p) for p in PRODUCTS}
    products_match = after == baseline

    caught_n = sum(r["status"] == "CAUGHT" for r in rows)
    dnr_n = sum(r["status"] == "DID NOT RUN" for r in rows)
    missed_n = sum(r["status"] == "MISSED" for r in rows)
    restored_n = sum(bool(r["restored"]) for r in rows)
    ok = (caught_n == len(cases) and dnr_n == 0 and missed_n == 0
          and restored_n == len(rows) and clean_green and products_match)
    selftest_expectations_met = (
        selftest and dnr_n == 1 and caught_n == len(CASES)
        and missed_n == 0 and restored_n == len(rows)
        and clean_green and products_match)

    out_path = (HERE / "data" / "mutation_separate_dnr_selftest.json"
                if selftest else OUT)
    report = {
        "cases": rows, "counts": {
            "total": len(rows), "caught": caught_n,
            "did_not_run": dnr_n, "missed": missed_n,
            "restored": restored_n},
        "clean_re_run": {"green": clean_green,
                         "returncode": clean.returncode,
                         "separate_models_ok": "SEPARATE_MODELS_OK" in clean_out},
        "products_sha_unchanged": products_match,
        "baseline": baseline, "after_clean": after,
        "selftest": selftest,
        "selftest_expectations_met": selftest_expectations_met,
        "ok": ok and not selftest,
    }
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    for r in rows:
        print("CASE", r["id"], r["status"], "restore", r["restored"],
              "reds", len(r.get("red_checks", [])), r["reason"])
    print("SUMMARY", json.dumps(report["counts"], ensure_ascii=False))
    print("CLEAN_GREEN", clean_green, "PRODUCTS_MATCH", products_match)
    print("MUTATION_SEPARATE_OK" if report["ok"]
          else "MUTATION_SEPARATE_FAILED")
    if selftest:
        print("SELFTEST_DNR_EFFECTIVE" if selftest_expectations_met
              else "SELFTEST_DNR_BROKEN")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
