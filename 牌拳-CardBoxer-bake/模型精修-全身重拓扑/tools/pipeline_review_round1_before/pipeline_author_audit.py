"""Diagnostic canonical assembly/acceptance, strictly within tools/ output paths.

This is not promotion. Authors may replace raw inputs while refining; record hashes.
"""
import json
from pathlib import Path
from canonical_glb import GLB,canonicalize,sha256
from check_retopology_assets import check_asset

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/"tools/pipeline_author_audit"
OUT.mkdir(exist_ok=True)
inventory=[]
for role in ("player","foe"):
    source=ROOT/"baseline/assets/3d"/(role+"-rigged.glb")
    raw=ROOT/"authoring"/role/(role+"-raw.glb")
    sockets=raw.parent/"contact-sockets.json";profile=OUT/(role+"-diagnostic-profile.json")
    output=OUT/(role+"-diagnostic-canonical.glb")
    g=GLB(source);parents={child:i for i,n in enumerate(g.doc["nodes"]) for child in n.get("children",[])}
    inventory.append(dict(role=role,source_sha256=sha256(source),nodes=g.doc["nodes"],skin=g.skin(),ibms=g.ibms().tolist(),
                          joints=[dict(name=g.doc["nodes"][i]["name"],node=i,parent=parents.get(i),global_matrix=g.globals()[i].tolist()) for i in g.skin()["joints"]]))
    raw_before=sha256(raw);sockets_before=sha256(sockets)
    try:
        bridge=canonicalize(source,raw,output,sockets,profile)
        (OUT/(role+"-bridge-report.json")).write_text(json.dumps(bridge,indent=2)+"\n",encoding="utf-8")
        report=check_asset(source,output,profile)
    except Exception as exc:
        report={"ok":False,"errors":[{"code":"canonicalize","detail":str(exc)}]}
    report.update(raw_sha256=raw_before,sockets_sha256=sockets_before,
                  inputs_stable_during_audit=raw_before==sha256(raw) and sockets_before==sha256(sockets))
    (OUT/(role+"-acceptance-report.json")).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print("DIAGNOSTIC_AUTHOR_ACCEPTANCE",role,json.dumps(report,indent=2),flush=True)
(OUT/"source-contract-inventory.json").write_text(json.dumps(inventory,indent=2)+"\n",encoding="utf-8")
