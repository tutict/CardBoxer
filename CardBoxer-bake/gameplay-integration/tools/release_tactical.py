"""Prepare or install the exact validated feature file set with baseline guards."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import shutil

TASK = Path(__file__).resolve().parents[1]
PROJECT = TASK/"project"
RELEASE = TASK/"release"
BASELINE = json.loads((TASK/"baseline-manifest.json").read_text(encoding="utf-8-sig"))
SOURCE = Path(BASELINE["source"]).resolve()
EXPECTED_SOURCE = (TASK.parent.parent/"CardBoxer").resolve()

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def checked(root, relative):
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise RuntimeError("Path escapes intended project: "+relative)
    return path

def previous_install():
    receipt_path = RELEASE/"installed.json"
    manifest_path = RELEASE/"manifest.json"
    if not receipt_path.exists() or not manifest_path.exists():
        return {}
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if (not receipt.get("verified") or receipt.get("source") != str(SOURCE)
            or Path(manifest.get("source","")).resolve() != SOURCE
            or receipt.get("files") != len(manifest.get("files",[]))):
        return {}
    baseline_by_path = {entry["path"]:entry["sha256"] for entry in BASELINE["files"]}
    installed = {}
    for entry in manifest["files"]:
        target = checked(SOURCE,entry["path"])
        payload = checked(RELEASE/"payload",entry["path"])
        backup = checked(RELEASE/"original",entry["path"])
        if not target.exists() or sha(target).upper() != entry["new_sha256"].upper():
            return {}
        if not payload.exists() or sha(payload).upper() != entry["new_sha256"].upper():
            return {}
        original_sha = baseline_by_path.get(entry["path"])
        if original_sha is not None:
            if not backup.exists() or sha(backup).upper() != original_sha.upper():
                return {}
        installed[entry["path"]] = entry
    return installed


def prepare():
    if SOURCE != EXPECTED_SOURCE:
        raise RuntimeError("Unexpected install target")
    managed = previous_install()
    baseline_by_path = {entry["path"]:entry["sha256"] for entry in BASELINE["files"]}
    files = ["project.godot","README.md","assets/tactical/hidden_card_back.png","assets/tactical/hidden_card_back.png.import","scripts/arena.gd","scripts/fighter.gd",
             "tests/taikou_flow_check.gd","tests/battle_integration_check.gd","tests/engine_opt_check.gd",
             "tools/verify_tactical.py","launch.bat","play-2d.bat","play.bat",
             "play-realtime.bat","play-classic.bat"]
    files += [str(p.relative_to(PROJECT)).replace("\\","/") for p in (PROJECT/"scripts").glob("tactical_*.gd")]
    files += [str(p.relative_to(PROJECT)).replace("\\","/") for p in (PROJECT/"tests").glob("tactical_*.gd")]
    entries, patches = [], []
    for relative in sorted(set(files)):
        old = checked(SOURCE,relative)
        current_hash = sha(old).upper() if old.exists() else None
        previous = managed.get(relative)
        baseline_hash = baseline_by_path.get(relative)
        if current_hash is not None:
            if previous is not None and current_hash == previous["new_sha256"].upper():
                pass
            elif previous is None and baseline_hash is not None and current_hash == baseline_hash.upper():
                pass
            else:
                raise RuntimeError("Install target differs from original or last verified install: "+relative)
        new = checked(PROJECT,relative)
        old = checked(SOURCE,relative)
        payload = checked(RELEASE/"payload",relative)
        original = checked(RELEASE/"original",relative)
        payload.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(new,payload)
        old_hash = sha(old) if old.exists() else None
        if old.exists() and relative not in managed and not original.exists():
            original.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(old,original)
        if new.suffix.lower() == ".png":
            before, after = [], []
        else:
            before = old.read_text(encoding="utf-8-sig").splitlines(keepends=True) if old.exists() else []
            after = new.read_text(encoding="utf-8-sig").splitlines(keepends=True)
            patches.extend(difflib.unified_diff(before,after,fromfile="a/"+relative,tofile="b/"+relative))
        entries.append({"path":relative,"old_sha256":old_hash,"new_sha256":sha(payload)})
    RELEASE.mkdir(parents=True,exist_ok=True)
    (RELEASE/"changes.patch").write_text("".join(patches),encoding="utf-8")
    (RELEASE/"manifest.json").write_text(json.dumps({"source":str(SOURCE),"files":entries},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"PREPARED: {len(entries)} files; last verified install accepted: {bool(managed)}")

def install():
    manifest = json.loads((RELEASE/"manifest.json").read_text(encoding="utf-8"))
    if SOURCE != EXPECTED_SOURCE or Path(manifest["source"]).resolve()!=SOURCE:
        raise RuntimeError("Unexpected install target")
    for entry in manifest["files"]:
        target = checked(SOURCE,entry["path"])
        current = sha(target) if target.exists() else None
        if current != entry["old_sha256"]:
            raise RuntimeError("Target changed since preparation: "+entry["path"])
        if sha(checked(RELEASE/"payload",entry["path"]))!=entry["new_sha256"]:
            raise RuntimeError("Payload changed since validation: "+entry["path"])
    for entry in manifest["files"]:
        target = checked(SOURCE,entry["path"])
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(checked(RELEASE/"payload",entry["path"]),target)
        if sha(target)!=entry["new_sha256"]:
            raise RuntimeError("Installed hash mismatch: "+entry["path"])
    (RELEASE/"installed.json").write_text(json.dumps({"source":str(SOURCE),"files":len(manifest["files"]),"verified":True},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"INSTALLED AND HASH-VERIFIED: {len(manifest['files'])} files")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--install",action="store_true")
    args=parser.parse_args()
    install() if args.install else prepare()
