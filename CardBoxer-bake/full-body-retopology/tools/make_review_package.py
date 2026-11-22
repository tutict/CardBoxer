"""Create a read-only review boundary from the immutable baseline and current files."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path

TASK = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scope", choices=("runtime", "pipeline", "player", "foe", "final"))
    parser.add_argument("--name", default="initial")
    args = parser.parse_args()
    if not args.name.replace("-", "").replace("_", "").isalnum():
        raise RuntimeError("Unsafe review package name")
    if args.scope == "runtime":
        paths = [TASK / "project" / name for name in (
            "scripts/hand_shape.gd", "scripts/native_motion.gd", "scripts/battle_presentation.gd",
            "scripts/fighter_3d_layer.gd", "tests/hand_shape_check.gd", "tests/hand_asset_check.gd")]
        paths += [TASK / "tools/author_hand_grips.py", TASK / "tools/check_hand_body.gd"]
    elif args.scope == "pipeline":
        paths = [TASK / "tools/canonical_glb.py", TASK / "tools/check_retopology_assets.py"]
        paths += sorted((TASK / "tools").glob("pipeline_*.py"))
    elif args.scope in ("player", "foe"):
        paths = [TASK / "tools" / ("author_" + args.scope + ".py")]
        paths += sorted((TASK / "authoring" / args.scope).glob("*.py"))
    else:
        paths = sorted((TASK / "project/scripts").glob("*.gd"))
        paths += [TASK / "tools/canonical_glb.py", TASK / "tools/check_retopology_assets.py",
                  TASK / "tools/release_candidate.py", TASK / "tools/run_candidate_checks.py",
                  TASK / "tools/check_full_body.py", TASK / "tools/check_hand_body.gd"]
    chunks = [f"Review boundary: {args.scope} / {args.name}\n",
              "No usable source Git history. BASE is the immutable installed V2 snapshot; HEAD is the hashed file boundary below.\n"]
    manifest = []
    for path in paths:
        if not path.is_file():
            continue
        relative = path.relative_to(TASK)
        original = TASK / "baseline" / path.relative_to(TASK / "project") if path.is_relative_to(TASK / "project") else None
        before = original.read_text(encoding="utf-8-sig") if original is not None and original.is_file() else ""
        after = path.read_text(encoding="utf-8-sig")
        if before == after:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.append({"path": str(path), "sha256": digest, "bytes": path.stat().st_size})
        chunks += ["\n" + str(path) + "\nSHA256: " + digest + "\n",
                   "".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                                fromfile=str(original or "absent-at-V2-baseline"), tofile=str(path), n=25))]
    chunks += ["\nStructured data boundary:\n"]
    for name in ("body-motion-contract.json", "candidate-checks.json", "full-body-geometry.json"):
        path = TASK / "reports" / name
        if path.is_file():
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            summary = {key: value for key, value in payload.items() if key not in ("roles", "checks")}
            chunks.append(str(path) + "\n" + json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    folder = TASK / "reports/reviews"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (args.scope + "-" + args.name + ".patch.txt")
    target.write_text("".join(chunks), encoding="utf-8")
    target.with_suffix(".manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"REVIEW_PACKAGE: {len(manifest)} changed code files, {target.stat().st_size} bytes")
    print(target)


if __name__ == "__main__":
    main()
