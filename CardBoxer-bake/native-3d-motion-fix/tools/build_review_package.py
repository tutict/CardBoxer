"""Package source changes against the immutable snapshot; no git state needed."""
from __future__ import annotations
import difflib
import hashlib
import json
from pathlib import Path

TASK = Path(__file__).resolve().parent.parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory() -> list[dict]:
    rows = []
    for path in sorted((TASK / "project").rglob("*")):
        if not path.is_file() or ".godot" in path.parts:
            continue
        rel = path.relative_to(TASK / "project").as_posix()
        base = TASK / "baseline" / rel
        after = digest(path)
        before = digest(base) if base.exists() else None
        if before != after:
            rows.append({"path": rel, "before": before, "after": after,
                         "bytes": path.stat().st_size})
    return rows


if __name__ == "__main__":
    rows = inventory()
    (TASK / "reports" / "change-manifest.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    patches = []
    for row in rows:
        rel = row["path"]
        path = TASK / "project" / rel
        base = TASK / "baseline" / rel
        if path.suffix not in {".gd", ".bat", ".md"}:
            continue
        old = base.read_text(encoding="utf-8-sig").splitlines(True) if base.exists() else []
        new = path.read_text(encoding="utf-8-sig").splitlines(True)
        patches.extend(difflib.unified_diff(old, new, fromfile="baseline/"+rel,
                                            tofile="project/"+rel, n=5))
    (TASK / "reports" / "review.patch").write_text("".join(patches), encoding="utf-8")
    print(f"Review package: {len(rows)} changed/new files")
    for row in rows:
        if not row["path"].endswith(".uid"):
            print(row["path"], row["bytes"])
