"""Hash-guarded publication of an independently accepted retopology candidate."""
from __future__ import annotations
import argparse
import copy
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

TASK = Path(__file__).resolve().parent.parent
PROJECT = TASK/'project'
MAIN = TASK.parent.parent/'CardBoxer'
GODOT = Path('C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe')
ALLOWED = {'.gd','.uid','.json','.glb','.png','.import','.bat','.md'}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def inside(root: Path, relative: str) -> Path:
    rel=Path(relative)
    if rel.is_absolute() or '..' in rel.parts: raise RuntimeError('Unsafe relative path: '+relative)
    result=(root/rel).resolve()
    if not result.is_relative_to(root.resolve()): raise RuntimeError('Path leaves its approved root: '+str(result))
    return result

def manifest() -> list[dict]:
    snapshot=read(TASK/'baseline-manifest.json')
    if Path(snapshot['source']).resolve()!=MAIN.resolve(): raise RuntimeError('Main target differs from source snapshot')
    original={r['path']:r for r in snapshot['files']}
    rows=[]
    for path in sorted(PROJECT.rglob('*')):
        if not path.is_file(): continue
        relative=path.relative_to(PROJECT).as_posix()
        if any(part.startswith('.') for part in Path(relative).parts): continue
        before=original.get(relative,{}).get('sha256')
        after=sha(path)
        if before==after: continue
        if path.suffix not in ALLOWED: raise RuntimeError('Unexpected publication file: '+relative)
        if len(Path(relative).parts)>1 and Path(relative).parts[0] not in ('assets','scripts','data','tests'):
            raise RuntimeError('File outside publication scope: '+relative)
        target=inside(MAIN,relative)
        current=sha(target) if target.exists() else None
        if current!=before: raise RuntimeError('Main file was edited since snapshot; preserve it: '+relative)
        rows.append({'path':relative,'before':before,'after':after,'bytes':path.stat().st_size,'target':str(target)})
    if not rows: raise RuntimeError('No retopology changes to publish')
    return rows

def engine(project: Path, script: str|None, tag: str, three_d: bool=False, mode: str='') -> dict:
    log=(TASK/'logs'/('release-'+tag+'-engine.log')).resolve()
    args=[str(GODOT),'--headless','--path',str(project),'--log-file',str(log)]
    args+=['--script','res://'+script] if script else ['--editor','--import']
    env=os.environ.copy()
    for key in tuple(env):
        if key.startswith(('CARD_BOXER_','NATIVE_','MODEL_DETAIL_')): env.pop(key,None)
    if three_d: env['CARD_BOXER_3D']='1'
    if mode: env['CARD_BOXER_BATTLE_MODE']=mode
    result=subprocess.run(args,env=env,capture_output=True,timeout=240,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    output=(result.stdout+result.stderr).decode('utf-8',errors='replace')
    (TASK/'logs'/('release-'+tag+'-output.log')).write_text(output,encoding='utf-8')
    errors=any(x in output for x in ('SCRIPT ERROR:','Parse Error:','Failed to load script','FAIL:','CrashHandlerException'))
    row={'name':tag,'ok':result.returncode==0 and not errors,'exit_code':result.returncode,'log':str(log),
        'summary':[line for line in output.splitlines() if 'CHECK' in line or 'PASS' in line or 'FAIL' in line]}
    print(tag+(': PASS' if row['ok'] else ': FAIL'),flush=True)
    if not row['ok']: raise RuntimeError('Engine verification failed: '+tag)
    return row

def verify_main() -> list[dict]:
    checks=[engine(MAIN,None,'installed-import')]
    for script in ('native_motion_check','native_rig_check','natural_runtime_check','hand_shape_check',
                   'hand_asset_check','battle_presentation_check','battle_transition_check',
                   'battle_contact_spacing_check','battle_shadow_check','motion_check',
                   'taikou_rules_check','taikou_flow_check'):
        if (MAIN/'tests'/(script+'.gd')).is_file():
            checks.append(engine(MAIN,'tests/'+script+'.gd','installed-'+script))
    for mode in ('taikou','realtime'):
        checks.append(engine(MAIN,'tests/battle_integration_check.gd','installed-3d-'+mode,True,mode))
    return checks

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--name',default='model-retopo-v1')
    args=parser.parse_args()
    if not args.name.replace('-','').isalnum(): raise RuntimeError('Unsafe release name')
    rows=manifest()
    preview={'target':str(MAIN),'name':args.name,'dry_run':not args.apply,'files':rows}
    (TASK/'reports/change-manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    (TASK/'reports/install-preview.json').write_text(json.dumps(preview,ensure_ascii=False,indent=2),encoding='utf-8')
    print(('Installing' if args.apply else 'Dry run')+f' {len(rows)} guarded files',flush=True)
    if not args.apply: return
    acceptance=read(TASK/'reports/final-acceptance.json')
    if not acceptance.get('ok'): raise RuntimeError('Final candidate has not been accepted')
    for row in rows:
        if acceptance.get('source_hashes',{}).get(row['path'])!=row['after']:
            raise RuntimeError('Candidate acceptance is stale: '+row['path'])
    before=TASK/'updates'/args.name/'before'
    if before.exists(): raise RuntimeError('Keep the existing recovery point; do not reinstall over it')
    before.mkdir(parents=True)
    previous=read(TASK/'reports/install-receipt-v2.json')
    (before.parent/'previous-receipt.json').write_text(json.dumps(previous,ensure_ascii=False,indent=2),encoding='utf-8')
    receipt=copy.deepcopy(previous)
    indexed={row['path']:row for row in receipt['files']}
    completed=[]
    for row in rows:
        source=inside(PROJECT,row['path']);target=inside(MAIN,row['path'])
        if sha(source)!=row['after']: raise RuntimeError('Candidate changed during publication: '+row['path'])
        current=sha(target) if target.exists() else None
        if current!=row['before']: raise RuntimeError('Main changed during publication: '+row['path'])
        if target.exists():
            backup=inside(before,row['path']);backup.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target,backup)
        target.parent.mkdir(parents=True,exist_ok=True)
        temporary=target.with_name(target.name+'.retopo-new')
        if temporary.exists(): raise RuntimeError('Unrelated temporary file exists: '+str(temporary))
        shutil.copy2(source,temporary)
        if sha(temporary)!=row['after']: raise RuntimeError('Temporary copy differs: '+row['path'])
        os.replace(temporary,target)
        if sha(target)!=row['after']: raise RuntimeError('Installed copy differs: '+row['path'])
        completed.append(row);indexed[row['path']]=row
        (before.parent/'update-receipt.json').write_text(json.dumps({'name':args.name,'files':completed},ensure_ascii=False,indent=2),encoding='utf-8')
    receipt['files']=list(indexed.values());receipt['last_update']=args.name
    receipt['updated_at']=datetime.datetime.now().astimezone().isoformat()
    (TASK/'reports/install-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.verify:
        checks=verify_main()
        (TASK/'reports/installed-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    # Keep the established main-game receipt current for subsequent motion tasks.
    established=TASK.parent/'native-3d-motion-fix/reports/install-receipt.json'
    established.write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print('RETOPO_INSTALL_COMPLETE: copies verified; V2 recovery retained',flush=True)

if __name__=='__main__': main()
