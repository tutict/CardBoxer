"""Add progressive hand controls without changing any V2 body/phase data."""
from __future__ import annotations
import json
from pathlib import Path

TASK = Path(__file__).resolve().parent.parent

def ease(value: float) -> float:
    p = min(1.0,max(0.0,value))
    return p*p*p*(p*(6*p-15)+10)

def mix(a: float,b: float,progress: float) -> float:
    return a+(b-a)*ease(progress)

def amount(clip: str,frame: float,total: int,split: list[int]) -> float:
    end = max(1.0,float(total-1))
    if clip=='ko': return mix(.75,0.0,frame/(end*.3))
    if clip in ('hit_light','hit_heavy'): return mix(.25,.75,frame/end)
    if clip=='block': return mix(1.0,.75,frame/end)
    if clip not in ('jab','cross','uppercut','wave','throw','guard'): return .75
    windup,active,_ = split
    contact = max(float(windup+active-1),float(windup))
    if clip=='guard':
        peak=max(1.0,float(windup))
        return mix(.75,1.0,frame/peak) if frame<=peak else mix(1.0,.75,(frame-peak)/max(1.0,end-peak))
    if clip in ('jab','cross','uppercut'):
        if frame<float(windup): return mix(.75,1.0,frame/max(1.0,float(windup-1)))
        if frame<=contact: return 1.0
        return mix(1.0,.75,(frame-contact)/max(1.0,end-contact))
    opened=max(1.0,float(windup)*.7)
    if frame<=opened: return mix(.75,0.0,frame/opened)
    if clip=='wave':
        if frame<=contact: return 0.0
        return mix(0.0,.75,(frame-contact)/max(1.0,end-contact))
    if frame<=contact: return mix(0.0,.65,(frame-opened)/max(.5,contact-opened))
    return mix(.65,.75,(frame-contact)/max(1.0,end-contact))

def main() -> None:
    source=TASK/'baseline/data/combat_motion_3d.json'
    destination=TASK/'project/data/combat_motion_3d.json'
    original=json.loads(source.read_text(encoding='utf-8'))
    data=json.loads(source.read_text(encoding='utf-8'))
    keys=0
    for role in ('player','foe'):
        for name,clip in data['roles'][role]['clips'].items():
            for key in clip['keys']:
                grip=amount(name,float(key['frame']),int(clip['frames']),clip['split'])
                key['hand_grip']=[grip,grip]
                keys+=1
    without_hands=json.loads(json.dumps(data))
    for role in without_hands['roles'].values():
        for clip in role['clips'].values():
            for key in clip['keys']: key.pop('hand_grip',None)
    assert without_hands==original,'V2 body/phase data must remain exact'
    destination.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (TASK/'reports/hand-grip-authoring.json').write_text(json.dumps({'keys':keys,'body_and_phase_exact':True},indent=2),encoding='utf-8')
    print(f'AUTHORED_HAND_GRIPS: {keys} keys; V2 body/phase data exact')

if __name__=='__main__': main()
