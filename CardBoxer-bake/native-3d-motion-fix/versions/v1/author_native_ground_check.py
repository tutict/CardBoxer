"""Actual mesh-sole grounding regression, using unchanged native GLB skinning."""
import json
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
from author_native_grounding import GLB,boot_masks

def sole_heights(glb, pose, masks):
    deformed = glb.deform(pose)
    return {s:float(deformed[m,1].min()) for s,m in masks.items()}

def main():
    data = json.loads((HERE/'project/data/combat_motion_3d.json').read_text(encoding='utf-8'))
    fails = []
    report = {}
    for role in ['player','foe']:
        glb = GLB(HERE/'project/assets/3d'/f'{role}-rigged.glb')
        masks = boot_masks(glb)
        clips = data['roles'][role]['clips']
        stats = []
        for cid in clips:
            for key in clips[cid]['keys']:
                height = sole_heights(glb,key,masks)
                support = ['b'] if cid in ['sweep','ko'] else ['f','b']
                # Walk plant alternates with each authored swing key.
                if cid=='walk': support = ['b'] if key['frame']<=17 else ['f']
                if cid in ['rush','backstep']:
                    support = [min(height,key=lambda side:abs(height[side]))]
                for suffix in support:
                    if abs(height[suffix]) > .012:
                        fails.append(f'{role}/{cid}@{key["frame"]} actual {suffix} boot sole y={height[suffix]:.5f}')
                stats.append({'clip':cid,'frame':key['frame'],'sole_y':height,'support':support})
        down = glb.deform(clips['ko']['keys'][-1])
        visible_min = float(down[:,1].min())
        if visible_min < -.025 or visible_min > .02:
            fails.append(f'{role}/ko final actual visible mesh floor y={visible_min:.5f}')
        report[role] = {'boot_vertices':{s:int(m.sum()) for s,m in masks.items()},'samples':stats,'ko_visible_min_y':visible_min}
        max_error = max(abs(row['sole_y'][s]) for row in stats for s in row['support'])
        report[role]['maximum_authored_support_sole_error_m'] = max_error
        print(role,'stance',stats[0]['sole_y'],'boot_vertices',report[role]['boot_vertices'],'ko_min',visible_min,'authored_keys',len(stats),'max_support_error',max_error)
    for failure in fails[:40]: print('FAIL:',failure)
    print('ACTUAL SOLE CHECK:', 'PASS' if not fails else 'FAIL', 'failures=',len(fails))
    (HERE/'reports/motion-actual-sole.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return 0 if not fails else 1

if __name__=='__main__': raise SystemExit(main())
