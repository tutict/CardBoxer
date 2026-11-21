"""Guarded incremental update from the last verified installation receipt."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
from install_verified_changes import TASK, PROJECT, TARGET, contained, digest, verify_engine


def prepare_update() -> list[dict]:
    receipt = json.loads((TASK/'reports/install-receipt.json').read_text(encoding='utf-8'))
    if Path(receipt['target']).resolve() != TARGET.resolve():
        raise RuntimeError('Receipt names another main project')
    expected = {row['path']:row['after'] for row in receipt['files']}
    original = json.loads((TASK/'baseline-manifest.json').read_text(encoding='utf-8-sig'))
    for row in original['files']:
        expected.setdefault(row['path'],row['sha256'])
    candidate = json.loads((TASK/'reports/change-manifest.json').read_text(encoding='utf-8'))
    changes = []
    for row in candidate:
        source = contained(PROJECT,row['path'])
        destination = contained(TARGET,row['path'])
        current = digest(destination) if destination.exists() else None
        if current != expected.get(row['path']):
            raise RuntimeError('Main file changed outside this task: '+row['path'])
        if digest(source) != row['after']:
            raise RuntimeError('Candidate manifest is stale: '+row['path'])
        if current != row['after']:
            changes.append(dict(row,before=current,target=str(destination)))
    return changes


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--name',default='natural-v2')
    args = parser.parse_args()
    if not args.name.replace('-','').isalnum():
        raise RuntimeError('Update name must contain only letters/numbers/hyphens')
    rows = prepare_update()
    preview={'target':str(TARGET),'name':args.name,'files':rows,'dry_run':not args.apply}
    (TASK/'reports/update-preview.json').write_text(json.dumps(preview,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"{'Updating' if args.apply else 'Dry run'} {len(rows)} guarded files",flush=True)
    if args.apply:
        backup=TASK/'updates'/args.name/'before'
        if backup.exists():
            raise RuntimeError('Update backup already exists; preserve the recovery point')
        backup.mkdir(parents=True)
        receipt=json.loads((TASK/'reports/install-receipt.json').read_text(encoding='utf-8'))
        updated={row['path']:row for row in receipt['files']}
        completed=[]
        for row in rows:
            source=contained(PROJECT,row['path'])
            destination=contained(TARGET,row['path'])
            current=digest(destination) if destination.exists() else None
            if current!=row['before']:
                raise RuntimeError('Main file changed during update: '+row['path'])
            if destination.exists():
                saved=contained(backup,row['path']);saved.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(destination,saved)
            destination.parent.mkdir(parents=True,exist_ok=True)
            temporary=destination.with_name(destination.name+'.native-update-new')
            if temporary.exists():
                raise RuntimeError('Unrelated temporary file exists: '+str(temporary))
            shutil.copy2(source,temporary)
            if digest(temporary)!=row['after']:
                raise RuntimeError('Temporary copy differs: '+row['path'])
            os.replace(temporary,destination)
            if digest(destination)!=row['after']:
                raise RuntimeError('Updated file differs: '+row['path'])
            updated[row['path']]=row;completed.append(row)
            receipt['files']=list(updated.values());receipt['last_update']=args.name
            (TASK/'reports/install-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
            (backup.parent/'update-receipt.json').write_text(json.dumps({'name':args.name,'files':completed},ensure_ascii=False,indent=2),encoding='utf-8')
        if args.verify:
            checks=verify_engine()
            (TASK/'reports/installed-checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
        print('UPDATE_COMPLETE: copies verified, versioned rollback saved',flush=True)
