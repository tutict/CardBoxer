"""Biomechanics regression on actual authored rig FK, without render assumptions.

The old open guard, bent high sweep and synchronous recovery must fail these
checks even when their sparse quaternions are perfectly eased by the runtime.
"""
import json
import math
from pathlib import Path
from author_native_motion import Rig, add, sub, qr, norm, dot, unit

HERE = Path(__file__).resolve().parent


def endpoint(rig, key):
    q, p = rig.globals(key['rotations'], key['root_offset'])
    for s in ['f', 'b']:
        p['hand_'+s] = add(p['forearm_'+s], qr(q['forearm_'+s], rig.tail['forearm_'+s]))
        p['foot_'+s] = add(p['shin_'+s], qr(q['shin_'+s], rig.tail['shin_'+s]))
    return p


def bend(a, joint, b):
    return math.degrees(math.acos(max(-1., min(1., dot(unit(sub(a,joint)), unit(sub(b,joint)))))))


def main():
    data = json.loads((HERE/'project/data/combat_motion_3d.json').read_text(encoding='utf-8'))
    measured = json.loads((HERE/'reports/rig-rest.json').read_text(encoding='utf-8-sig'))
    failures = []
    report = {}
    def check(ok, label):
        if not ok: failures.append(label)
    for role in ['player','foe']:
        source = json.loads((HERE/('project/data/motion_input.json' if role=='player' else 'project/data/motion_input_foe.json')).read_text(encoding='utf-8-sig'))
        rig = Rig(role, measured['roles'][role], source)
        clips = data['roles'][role]['clips']
        guard = endpoint(rig, clips['stance']['keys'][0])
        metrics = {}
        for side in ['f','b']:
            reach = norm(sub(guard['hand_'+side],guard['upperarm_'+side])) / rig.arm[side]
            angle = bend(guard['upperarm_'+side],guard['forearm_'+side],guard['hand_'+side])
            check(reach < .64 and angle < 85., f'{role} {side} guard compact bent elbow, not open presentation (reach={reach:.3f}, angle={angle:.1f})')
            chin_offset = guard['hand_'+side][1]-guard['head'][1]
            check(-.095 < chin_offset < -.01, f'{role} {side} guard wrist beside cheek/chin below head origin (offset={chin_offset:.3f})')
            check(guard['hand_'+side][2]-guard['upperarm_'+side][2] > .20, f'{role} {side} guard remains visible clear of chest')
            check(guard['forearm_'+side][1] < guard['upperarm_'+side][1], f'{role} {side} guard elbow hangs below shoulder')
            metrics['guard_'+side] = {'reach_ratio':reach,'elbow_angle_deg':angle,'wrist_y_relative_head_m':chin_offset}
        sweep = clips['sweep']
        contact = next(k for k in sweep['keys'] if k['frame']==sweep['contact_frame'])
        points = endpoint(rig,contact)
        angle = bend(points['thigh_f'],points['shin_f'],points['foot_f'])
        sole = rig.boot_grounder.sole(contact,'f')
        check(angle > 132., f'{role} sweep contact leg extended instead of raised knee (angle={angle:.1f})')
        check(.015 <= sole <= .075, f'{role} sweep striking boot travels close to floor (sole={sole:.3f})')
        check(abs(points['foot_f'][2]-(.79 if role=='player' else .67)) < .002, f'{role} sweep preserves calibrated contact reach, z={points["foot_f"][2]:.3f}')
        metrics['sweep'] = {'knee_angle_deg':angle,'contact_sole_y':sole}
        rear_plant = endpoint(rig,sweep['keys'][0])['foot_b']
        lateral = max(endpoint(rig,k)['foot_f'][0] for k in sweep['keys'] if k['frame'] < sweep['contact_frame'])
        check(lateral > .45, f'{role} sweep passes laterally around the planted leg')
        for k in sweep['keys']:
            p = endpoint(rig,k)
            check(abs(p['foot_b'][0]-rear_plant[0])+abs(p['foot_b'][2]-rear_plant[2]) < .00001, f'{role} sweep rear ankle stays planted throughout turn at {k["frame"]}')
        for cid in ['jab','cross','sweep','uppercut','wave','throw','walk','hit_light','ko']:
            clip = clips[cid]
            gaps = [b['frame']-a['frame'] for a,b in zip(clip['keys'],clip['keys'][1:])]
            check(max(gaps) <= .500001, f'{role}/{cid} target-space trajectory solved throughout the arc, maximum key gap={max(gaps):.2f}')
        for cid, side in [('jab','f'),('cross','b')]:
            clip = clips[cid]
            c = clip['contact_frame']
            first = endpoint(rig,clip['keys'][0])
            pullback = max(first['hand_'+side][2]-endpoint(rig,k)['hand_'+side][2] for k in clip['keys'] if k['frame'] <= c)
            check(pullback < (.105 if cid=='jab' else .19), f'{role}/{cid} economical chamber, pullback={pullback:.3f}')
            # By 70% of recovery the hand is protected while weight/torso still settle.
            recovery = min(clip['keys'],key=lambda k:abs(k['frame']-(c+(clip['frames']-1-c)*.70)))
            p = endpoint(rig,recovery)
            local_hand = sub(p['hand_'+side],p['upperarm_'+side])
            guard_hand = sub(guard['hand_'+side],guard['upperarm_'+side])
            check(norm(sub(local_hand,guard_hand)) < .075, f'{role}/{cid} hand regains guard before weight settles')
            residual = norm(sub(recovery['root_offset'],clip['keys'][-1]['root_offset']))
            check(residual > .003, f'{role}/{cid} trailing body settle follows recovered hand')
            metrics[cid] = {'maximum_hand_pullback_m':pullback,'late_hand_guard_error_m':norm(sub(local_hand,guard_hand)),'late_root_residual_m':residual}
        cross_clip = clips['cross']
        wind = next(k for k in cross_clip['keys'] if k['frame']==cross_clip['split'][0]-1)
        turn = next(k for k in cross_clip['keys'] if k['frame']==cross_clip['split'][0])
        impact = next(k for k in cross_clip['keys'] if k['frame']==cross_clip['contact_frame'])
        def hip_yaw(k):
            forward = qr(k['rotations']['hips'],(0.,0.,1.))
            return math.atan2(forward[0],forward[2])
        hip_progress = (hip_yaw(turn)-hip_yaw(wind))/(hip_yaw(impact)-hip_yaw(wind))
        def hand_extension(k):
            p = endpoint(rig,k)
            return norm(sub(p['hand_b'],p['upperarm_b']))
        hand_progress = (hand_extension(turn)-hand_extension(wind))/(hand_extension(impact)-hand_extension(wind))
        check(hip_progress > .65 and hand_progress < .55, f'{role} cross hip turns before rear fist extends (hip={hip_progress:.2f}, fist={hand_progress:.2f})')
        metrics['cross']['early_active_hip_progress'] = hip_progress
        metrics['cross']['early_active_fist_progress'] = hand_progress
        report[role] = metrics
    for failure in failures: print('FAIL:',failure)
    print('NATURAL AUTHOR FLOW CHECK:', 'PASS' if not failures else 'FAIL', 'failures=',len(failures))
    (HERE/'reports/natural-author-metrics.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return 0 if not failures else 1


if __name__=='__main__': raise SystemExit(main())
