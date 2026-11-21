"""Author continuous target-space 3D combat trajectories on each measured rig.

Source timing and leaf-tail geometry come from motion_input*.json; boot-floor
calibration measures current GLB skin vertices. No old 2D trajectory or retarget
amplitude is consumed. Reproducible; uses shared read-only NumPy skin helpers.
"""
import copy
import json
import math
from pathlib import Path
import re
from author_native_grounding import BootGrounder

HERE = Path(__file__).resolve().parent
BONES = ['hips', 'spine', 'chest', 'neck', 'head', 'upperarm_f', 'forearm_f',
         'upperarm_b', 'forearm_b', 'thigh_f', 'shin_f', 'thigh_b', 'shin_b']

def add(a, b): return tuple(x + y for x, y in zip(a, b))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def mul(a, s): return tuple(x * s for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def norm(a): return math.sqrt(dot(a, a))
def unit(a): return mul(a, 1.0 / norm(a))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
IDENTITY = (0., 0., 0., 1.)

def qm(a, b):
    v = add(add(mul(b[:3], a[3]), mul(a[:3], b[3])), cross(a[:3], b[:3]))
    return (*v, a[3]*b[3] - dot(a[:3], b[:3]))

def qi(q): return (-q[0], -q[1], -q[2], q[3])
def qr(q, v): return qm(qm(q, (*v, 0.)), qi(q))[:3]

def axis(a, degrees):
    a = unit(a)
    h = math.radians(degrees)*.5
    return (*mul(a, math.sin(h)), math.cos(h))

def euler(pitch=0., yaw=0., roll=0.):
    return qm(qm(axis((0,1,0), yaw), axis((1,0,0), pitch)), axis((0,0,1), roll))

def swing(a, b):
    a, b = unit(a), unit(b)
    d = dot(a, b)
    if d < -.999999:
        normal = cross(a, (0,1,0))
        if norm(normal) < .001: normal = cross(a, (1,0,0))
        return axis(normal, 180)
    return unit((*cross(a,b), 1.+d))

class Rig:
    def __init__(self, role, measured, source):
        self.role = role
        self.source = source
        self.b = {b['name']: b for b in measured['bones'] if b['name'] in BONES}
        self.restq = {n: unit(self.b[n]['local_rest']['quaternion']) for n in BONES}
        self.grestq = {n: unit(self.b[n]['global_rest']['quaternion']) for n in BONES}
        self.restp = {n: tuple(self.b[n]['global_rest']['origin']) for n in BONES}
        self.lp = {n: tuple(self.b[n]['local_rest']['origin']) for n in BONES}
        self.tail = {}
        for kind, suffix, source_name in [('forearm','f','f_hand'), ('forearm','b','b_hand'),
                                          ('shin','f','f_foot'), ('shin','b','b_foot')]:
            n = kind + '_' + suffix
            endpoint = source['apose_points'][source_name]
            self.tail[n] = qr(qi(self.grestq[n]), sub((endpoint[0],endpoint[1],0.), self.restp[n]))
        self.arm = {s: norm(sub(self.restp['forearm_'+s],self.restp['upperarm_'+s])) + norm(self.tail['forearm_'+s]) for s in ['f','b']}
        # Wrist/tail targets clear the chest and lift the unchanged hand meshes
        # into a readable chin guard. The armored role needs less vertical gain.
        self.guard_hands = {'f':(.09,.225,.40),'b':(-.10,.24,.29)} if role=='player' else {'f':(.09,.175,.40),'b':(-.10,.16,.405)}
        self.height = self.restp['hips'][1]
        self.ground = source['apose_points']['f_foot'][1]
        self.max_ik_error = 0.
        self.boot_grounder = BootGrounder(role)
        self.max_sole_error = 0.

    def globals(self, local, root):
        q, p = {}, {}
        remaining = list(BONES)
        while remaining:
            for n in remaining[:]:
                parent = self.b[n]['parent']
                if parent and parent not in q: continue
                pq = q.get(parent, IDENTITY)
                q[n] = qm(pq, qm(self.restq[n], local[n]))
                p[n] = add(p.get(parent, (0.,0.,0.)), qr(pq, self.lp[n]))
                if n == 'hips': p[n] = add(p[n], root)
                remaining.remove(n)
        return q, p

    def orient(self, local, root, n, direction, roll=0.):
        q, _ = self.globals(local, root)
        rest_axis = self.lp['forearm_'+n[-1]] if n.startswith('upperarm') else self.lp['shin_'+n[-1]] if n.startswith('thigh') else self.tail[n]
        desired = qm(swing(qr(self.grestq[n],rest_axis), direction), self.grestq[n])
        desired = qm(axis(direction,roll),desired)
        parent = self.b[n]['parent']
        local[n] = unit(qm(qi(self.restq[n]), qm(qi(q.get(parent,IDENTITY)),desired)))

    def ik(self, local, root, upper, lower, target, pole, roll=0.):
        _, p = self.globals(local,root)
        start = p[upper]
        length1 = norm(self.lp[lower])
        length2 = norm(self.tail[lower])
        direction = sub(target,start)
        distance = min(max(norm(direction), abs(length1-length2)+.0001), (length1+length2)*.994)
        forward = unit(direction)
        bend = sub(pole,mul(forward,dot(pole,forward)))
        if norm(bend) < .0001: bend = cross(forward,(1.,0.,0.))
        bend = unit(bend)
        along = (length1*length1-length2*length2+distance*distance)/(2*distance)
        perpendicular = math.sqrt(max(0.,length1*length1-along*along))
        joint = add(start,add(mul(forward,along),mul(bend,perpendicular)))
        reachable = add(start,mul(forward,distance))
        self.orient(local,root,upper,sub(joint,start),roll)
        self.orient(local,root,lower,sub(reachable,joint),roll)
        self.max_ik_error = max(self.max_ik_error, norm(sub(reachable,target)))

    def pose(self, **changes):
        cfg = dict(pitch=5.,yaw=-10.,lean=0.,crouch=.12 if self.role=='player' else .105,
                   root_x=0.,root_z=0., chest_pitch=2.,chest_yaw=0.,chest_roll=0.,
                   hands=self.guard_hands,
                   feet={'f':(.16,0.,.24),'b':(-.16,0.,-.22)}, rolls={'f':-58.,'b':58.},
                   arm_poles={'f':(.20,-1.,.10),'b':(-.20,-1.,.10)},
                   hip_yaw=None,spine_yaw=None)
        cfg.update(changes)
        if cfg['hip_yaw'] is None: cfg['hip_yaw'] = cfg['yaw']*.55
        if cfg['spine_yaw'] is None: cfg['spine_yaw'] = cfg['yaw']*.45
        root = (cfg['root_x'],-cfg['crouch'],cfg['root_z'])
        local = {n: IDENTITY for n in BONES}
        local['hips'] = euler(cfg['pitch']*.25,cfg['hip_yaw'],cfg['lean']*.3)
        local['spine'] = euler(cfg['pitch']*.75,cfg['spine_yaw'],cfg['lean']*.7)
        local['chest'] = euler(cfg['chest_pitch'],cfg['chest_yaw'],cfg['chest_roll'])
        # Keep the face looking toward the opponent as the shoulders torque.
        local['neck'] = euler(-cfg['pitch']*.20,-cfg['chest_yaw']*.20,-cfg['lean']*.15)
        local['head'] = euler(-cfg['pitch']*.45,-(cfg['yaw']+cfg['chest_yaw'])*.45,-cfg['lean']*.45)
        for suffix in ['f','b']:
            _, p = self.globals(local,root)
            hand = cfg['hands'][suffix]
            target = add(p['upperarm_'+suffix],mul(hand,self.arm[suffix]))
            sign = 1. if suffix=='f' else -1.
            self.ik(local,root,'upperarm_'+suffix,'forearm_'+suffix,target,cfg['arm_poles'][suffix],cfg['rolls'][suffix])
        for suffix in ['f','b']:
            foot = cfg['feet'][suffix]
            target = (foot[0],self.ground+foot[1],foot[2])
            sign = 1. if suffix=='f' else -1.
            # Bone-tail y is not a shoe sole: calf orientation rotates the toe
            # below it. Solve the original weighted boot vertices against floor.
            for _ in range(14):
                self.ik(local,root,'thigh_'+suffix,'shin_'+suffix,target,(sign*.15,0.,1.))
                actual = self.boot_grounder.sole({'rotations':local,'root_offset':root},suffix)
                error = actual - foot[1]
                if abs(error) < .00002: break
                target = (target[0],target[1]-max(-.10,min(.10,error)),target[2])
            self.max_sole_error = max(self.max_sole_error,abs(error))
        return {'rotations': {n: [round(v,9) for v in unit(local[n])] for n in BONES},
                'root_offset': [round(v,9) for v in root], '_targets':copy.deepcopy(cfg)}

def key(frame, pose): return {'frame':frame,**copy.deepcopy(pose)}

def dense_targets(rig, clip):
    """C1 monotone Hermite in target space, then solve/ground every half-frame.

    A zero tangent is used only at a true scalar reversal or held value. This
    avoids smoothstep's whole-pose halt at every breakdown and avoids cubic
    foot lift/plant overshoot. Runtime cubic sampling is a separate small-step
    approximation, not an IK or floor correction in the game.
    """
    authored = clip['keys']
    times = [k['frame'] for k in authored]
    configs = [k['_targets'] for k in authored]
    def scalar(values, interval, frame):
        def tangent(i):
            if i == 0 or i == len(values)-1: return 0.
            h0,h1 = times[i]-times[i-1],times[i+1]-times[i]
            d0,d1 = (values[i]-values[i-1])/h0,(values[i+1]-values[i])/h1
            if d0*d1 <= 0.: return 0.
            w0,w1 = 2.*h1+h0,h1+2.*h0
            return (w0+w1)/(w0/d0+w1/d1)
        i = interval
        h = times[i+1]-times[i]
        t = (frame-times[i])/h
        return ((2*t**3-3*t*t+1)*values[i]+(t**3-2*t*t+t)*h*tangent(i)
                +(-2*t**3+3*t*t)*values[i+1]+(t**3-t*t)*h*tangent(i+1))
    def interpolate(values, interval, frame):
        first = values[0]
        if isinstance(first,dict): return {name:interpolate([v[name] for v in values],interval,frame) for name in first}
        if isinstance(first,(tuple,list)): return tuple(interpolate([v[j] for v in values],interval,frame) for j in range(len(first)))
        return scalar(values,interval,frame)
    if len(authored)==1:
        clip['keys'] = [{k:v for k,v in authored[0].items() if k!='_targets'}]
        clip['interpolation'] = 'continuous'
        return
    by_time = {k['frame']:k for k in authored}
    dense = []
    interval = 0
    for half in range((clip['frames']-1)*2+1):
        frame = half*.5
        if frame in by_time:
            result = by_time[frame]
        else:
            while interval+1<len(times)-1 and frame>times[interval+1]: interval+=1
            result = key(frame,rig.pose(**interpolate(configs,interval,frame)))
        dense.append({k:v for k,v in result.items() if k!='_targets'})
    clip['keys'] = dense
    clip['interpolation'] = 'continuous'

def timing():
    text = (HERE/'project/scripts/card_data.gd').read_text(encoding='utf-8')
    found = {}
    for m in re.finditer(r'^\t"(\w+)": \{(.*?)^\t\},',text,re.M|re.S):
        body = m[2]
        values = [int(re.search(r'"'+n+r'": (\d+)',body)[1]) for n in ['windup','active','recover']]
        found[m[1]] = values
    assert len(found)==12
    return found

def build(rig, splits):
    guard = rig.pose()
    pose = rig.pose
    fguard, bguard = rig.guard_hands['f'], rig.guard_hands['b']
    clips = {'stance':{'frames':1,'split':[0,0,1],'contact_frame':-1,'keys':[key(0,guard)]}}
    def card(cid, wind, impact, overshoot, recovery=None, extra=None):
        split = splits[cid]
        frames = sum(split)
        assert rig.source['cards'][cid]['frames']==frames
        contact = split[0]+split[1]-1
        keys = [key(0,guard),key(split[0]-1,wind),key(contact,impact),
                key(min(frames-2,contact+max(2,split[2]//3)),overshoot)]
        if recovery is not None: keys.append(key(frames-3,recovery))
        if extra: keys.extend(extra)
        keys.append(key(frames-1,guard))
        keyed = {k['frame']:k for k in keys}
        clips[cid] = {'frames':frames,'split':split,'contact_frame':contact,'keys':[keyed[f] for f in sorted(keyed)]}
    card('jab',pose(yaw=-13.,root_z=-.009,hip_yaw=-3.,hands={'f':add(fguard,(0.,-.03,-.06)),'b':bguard}),
         pose(pitch=9.,yaw=-15.,root_z=.035,crouch=.13,hip_yaw=-3.,spine_yaw=-12.,chest_yaw=3.,hands={'f':(.13,.025,.948),'b':bguard},rolls={'f':-80.,'b':58.}),
         pose(pitch=8.,yaw=-13.,root_z=.023,crouch=.13,chest_yaw=2.,hands={'f':add(fguard,(.005,-.01,.03)),'b':bguard},rolls={'f':-48.,'b':58.}),
         pose(pitch=6.,yaw=-11.,root_z=.008,crouch=.123,hands={'f':fguard,'b':bguard}),
         [key(4,pose(pitch=7.,yaw=-13.,root_z=.012,crouch=.13,hip_yaw=-2.,spine_yaw=-11.,hands={'f':(.105,.19,.66),'b':bguard},rolls={'f':-60.,'b':58.}))])
    card('cross',pose(yaw=-25.,pitch=3.,root_z=-.025,crouch=.16,hip_yaw=-9.,spine_yaw=-16.,chest_yaw=-7.,hands={'f':fguard,'b':(-.11,.22,.29)}),
         pose(pitch=12.,yaw=24.,root_z=.035,crouch=.15,chest_yaw=16.,hands={'f':fguard,'b':(-.09,.01,.948)},rolls={'f':-58.,'b':80.}),
         pose(yaw=31.,pitch=10.,root_z=.032,crouch=.15,chest_yaw=12.,hands={'f':fguard,'b':(-.11,.31,.42)},rolls={'f':-58.,'b':48.}),
         pose(yaw=-13.,pitch=6.,root_z=.009,crouch=.125,chest_yaw=1.,hands={'f':fguard,'b':bguard}),
         [key(6,pose(yaw=-1.,pitch=7.,root_z=.007,crouch=.155,hip_yaw=9.,spine_yaw=-10.,chest_yaw=-3.,hands={'f':fguard,'b':(-.11,.17,.46)},rolls={'f':-58.,'b':45.})),
          key(16,pose(yaw=9.,pitch=8.,root_z=.019,crouch=.14,chest_yaw=6.,hands={'f':fguard,'b':bguard}))])
    rear = (-.16,0.,-.22)
    sweep_crouch = .38 if rig.role=='player' else .21
    card('sweep',pose(crouch=sweep_crouch,pitch=28.,yaw=-31.,root_z=-.035,feet={'f':(.32,.035,-.42),'b':rear},hands={'f':(.18,.18,.40),'b':bguard}),
         pose(crouch=sweep_crouch,pitch=29.,yaw=22.,root_z=-.02,chest_yaw=10.,feet={'f':(.13,.04,.79 if rig.role=='player' else .67),'b':rear},hands={'f':(.18,.15,.41),'b':bguard}),
         pose(crouch=sweep_crouch+.025,pitch=25.,yaw=33.,root_z=-.015,feet={'f':(-.23,.045,.55),'b':rear},hands={'f':(.13,.23,.42),'b':bguard}),
         pose(crouch=.18,yaw=-13.,root_z=-.008,feet={'f':(.16,0.,.24),'b':rear}),
         [key(9,pose(crouch=sweep_crouch,pitch=29.,yaw=-8.,root_z=-.03,hip_yaw=4.,spine_yaw=-12.,feet={'f':(.62 if rig.role=='player' else .52,.04,.10),'b':rear},hands={'f':(.18,.17,.40),'b':bguard})),
          key(22,pose(crouch=.22,pitch=14.,yaw=9.,root_z=-.011,feet={'f':(.16,0.,.24),'b':rear}))])
    card('uppercut',pose(crouch=.27,pitch=21.,yaw=-25.,root_z=-.022,chest_yaw=-6.,hands={'f':(.12,-.22,.29),'b':bguard}),
         pose(crouch=.075,pitch=-3.,yaw=18.,root_z=.025,chest_pitch=-9.,chest_yaw=6.,hands={'f':(.10,.68,.64),'b':bguard},rolls={'f':-105.,'b':58.}),
         pose(crouch=.06,pitch=-7.,yaw=25.,root_z=.025,chest_pitch=-5.,hands={'f':(.11,.56,.49),'b':bguard},rolls={'f':-75.,'b':58.}),
         pose(crouch=.125,pitch=6.,yaw=-12.,root_z=.008,hands={'f':fguard,'b':bguard}),
         [key(7,pose(crouch=.185,pitch=15.,yaw=-6.,root_z=.0,hip_yaw=7.,spine_yaw=-13.,chest_yaw=-3.,hands={'f':(.10,-.06,.47),'b':bguard},rolls={'f':-90.,'b':58.})),
          key(8,pose(crouch=.13,pitch=7.,yaw=7.,root_z=.012,chest_yaw=1.,hands={'f':(.10,.24,.67),'b':bguard},rolls={'f':-105.,'b':58.})),
          key(18,pose(crouch=.10,pitch=0.,yaw=9.,root_z=.018,chest_pitch=-2.,hands={'f':fguard,'b':bguard}))])
    card('wave',pose(crouch=.215,pitch=-3.,yaw=-23.,root_z=-.035,chest_yaw=-12.,hands={'f':(.12,-.17,.25),'b':(-.12,-.15,.22)},rolls={'f':28.,'b':-28.}),
         pose(crouch=.17,pitch=15.,yaw=-3.,root_z=.035,hands={'f':(.16,-.01,.93),'b':(-.16,-.01,.93)},rolls={'f':38.,'b':-38.}),
         pose(crouch=.205,pitch=17.,yaw=3.,root_z=.03,hands={'f':(.15,-.02,.84),'b':(-.15,-.02,.84)},rolls={'f':38.,'b':-38.}),
         pose(crouch=.125,pitch=5.,root_z=.008,hands={'f':fguard,'b':bguard}),
         [key(10,pose(crouch=.19,pitch=9.,yaw=-8.,root_z=.005,hip_yaw=1.,spine_yaw=-9.,hands={'f':(.13,-.04,.72),'b':(-.13,-.04,.72)},rolls={'f':38.,'b':-38.})),
          key(29,pose(crouch=.15,pitch=9.,yaw=1.,root_z=.015,hands={'f':fguard,'b':bguard}))])
    card('throw',pose(crouch=.18,pitch=10.,yaw=-18.,root_z=.004,hands={'f':(.14,.13,.68),'b':(-.14,.12,.64)}),
         pose(crouch=.24,pitch=18.,yaw=28.,root_z=.024,chest_yaw=25.,hands={'f':(-.03,-.03,.85),'b':(-.16,-.02,.86)},rolls={'f':25.,'b':-20.}),
         pose(crouch=.19,pitch=13.,yaw=48.,root_z=.026,chest_yaw=20.,hands={'f':(-.26,-.06,.50),'b':(-.35,-.08,.45)},rolls={'f':25.,'b':-20.}),
         pose(yaw=-13.,pitch=6.,crouch=.126,root_z=.008,hands={'f':fguard,'b':bguard}),
         [key(5,pose(crouch=.205,pitch=15.,yaw=-3.,root_z=.01,hip_yaw=6.,spine_yaw=-9.,hands={'f':(.12,.075,.87),'b':(-.12,.075,.87)},rolls={'f':25.,'b':-20.})),
          key(6,pose(crouch=.275,pitch=20.,yaw=5.,root_z=.011,chest_yaw=3.,hands={'f':(.07,-.015,.82),'b':(-.13,-.01,.85)},rolls={'f':25.,'b':-20.})),
          key(16,pose(crouch=.15,pitch=9.,yaw=23.,root_z=.017,chest_yaw=8.,hands={'f':fguard,'b':bguard}))])

    def utility(cid, wind, peak, settle, extra=None):
        split = splits[cid]
        frames = sum(split)
        assert rig.source['cards'][cid]['frames']==frames
        a = split[0]-1
        b = split[0]+max(1,split[2]//3)
        c = min(frames-2,b+max(2,split[2]//3))
        keyed = {0:key(0,guard),a:key(a,wind),b:key(b,peak),c:key(c,settle),frames-1:key(frames-1,guard)}
        if extra:
            for k in extra: keyed[k['frame']] = k
        clips[cid] = {'frames':frames,'split':split,'contact_frame':-1,'keys':[keyed[f] for f in sorted(keyed)]}

    utility('rush',pose(crouch=.22,pitch=23.,hands={'f':(.22,.02,.51),'b':(-.31,-.02,.32)},feet={'f':(.16,0.,.16),'b':(-.16,0.,-.29)}),
            pose(crouch=.16,pitch=29.,root_z=.06,hands={'f':(.19,.03,.67),'b':(-.32,-.14,.27)},feet={'f':(.16,.06,.39),'b':(-.16,0.,-.22)}),
            pose(crouch=.15,pitch=12.,feet={'f':(.16,0.,.24),'b':(-.16,.055,-.06)}),
            [key(8.5,pose(crouch=.17,pitch=20.,root_z=.025,feet={'f':(.16,0.,.24),'b':(-.16,0.,-.22)}))])
    utility('backstep',pose(crouch=.21,pitch=-7.,hands={'f':(.22,.16,.59),'b':(-.22,.18,.43)}),
            pose(crouch=.15,pitch=-17.,root_z=-.06,feet={'f':(.16,.06,.08),'b':(-.16,0.,-.35)},hands={'f':(.25,.19,.60),'b':(-.25,.16,.48)}),
            pose(crouch=.13,pitch=-2.,feet={'f':(.16,0.,.24),'b':(-.16,.04,-.24)}),
            [key(6.5,pose(crouch=.145,pitch=-10.,root_z=-.025,feet={'f':(.16,0.,.24),'b':(-.16,0.,-.27)}))])
    utility('guard',pose(crouch=.20,pitch=12.,hands={'f':(.09,.43,.43),'b':(-.09,.44,.42)},chest_roll=-4.),
            pose(crouch=.22,pitch=14.,hands={'f':(.08,.45,.41),'b':(-.08,.46,.40)},chest_roll=-5.),
            pose(crouch=.15,pitch=9.,hands={'f':(.10,.39,.44),'b':(-.10,.40,.42)}))
    utility('sidestep',pose(crouch=.22,pitch=14.,lean=17.,root_x=.08,yaw=-24.,hands={'f':(.31,.16,.38),'b':(-.14,.20,.48)}),
            pose(crouch=.27,pitch=22.,lean=25.,root_x=.12,yaw=-35.,feet={'f':(.22,0.,.24),'b':(-.12,0.,-.22)},hands={'f':(.34,.20,.32),'b':(-.16,.22,.47)}),
            pose(crouch=.16,pitch=5.,lean=-9.,root_x=-.035,yaw=-6.))
    utility('focus',pose(crouch=.20,pitch=-2.,yaw=0.,hands={'f':(.17,-.22,.34),'b':(-.17,-.22,.32)},rolls={'f':25.,'b':-25.}),
            pose(crouch=.15,pitch=-5.,yaw=0.,chest_pitch=-3.,hands={'f':(.19,-.18,.39),'b':(-.19,-.18,.37)},rolls={'f':25.,'b':-25.}),
            pose(crouch=.17,pitch=2.,yaw=-5.,hands={'f':(.22,-.07,.44),'b':(-.22,-.06,.41)}))
    utility('recover',pose(crouch=.26,pitch=21.,yaw=-23.,chest_roll=7.,hands={'f':(.31,-.16,.44),'b':(-.19,.04,.35)}),
            pose(crouch=.19,pitch=-8.,yaw=5.,chest_roll=-7.,hands={'f':(.33,.08,.58),'b':(-.32,.09,.46)}),
            pose(crouch=.14,pitch=3.,yaw=-15.,hands={'f':(.24,.12,.48),'b':(-.24,.12,.37)}))

    def auxiliary(cid, authored, frames=None):
        if frames is None: frames = rig.source['cards'][cid]['frames']
        clips[cid] = {'frames':frames,'split':[0,1,frames-1],'contact_frame':-1,
                      'keys':[key(f,p) for f,p in authored]}
    light_impact = pose(crouch=.17,pitch=-16.,yaw=-22.,lean=-7.,chest_pitch=-10.,hands={'f':(.27,.16,.34),'b':(-.29,.18,.24)})
    heavy_impact = pose(crouch=.27,pitch=-27.,yaw=16.,lean=-16.,chest_pitch=-13.,hands={'f':(.36,.12,.28),'b':(-.31,.06,.21)})
    block_impact = pose(crouch=.25,pitch=-7.,yaw=-18.,hands={'f':(.09,.45,.43),'b':(-.09,.46,.42)},chest_roll=-6.)
    auxiliary('hit_light',[(0,light_impact),(3,pose(crouch=.18,pitch=-21.,yaw=-28.,lean=-9.,hands={'f':(.29,.12,.31),'b':(-.29,.14,.26)})),(9,pose(crouch=.17,pitch=12.,yaw=-4.)),(15,guard)])
    auxiliary('hit_heavy',[(0,heavy_impact),(5,pose(crouch=.30,pitch=-34.,yaw=24.,lean=-22.,hands={'f':(.40,-.02,.26),'b':(-.38,-.05,.22)})),(15,pose(crouch=.29,pitch=28.,yaw=-21.,lean=10.,hands={'f':(.31,-.16,.40),'b':(-.25,-.11,.33)})),(24,pose(crouch=.14,pitch=-3.,yaw=-15.)),(29,guard)])
    auxiliary('block',[(0,block_impact),(2,pose(crouch=.28,pitch=-11.,yaw=-24.,hands={'f':(.09,.44,.39),'b':(-.09,.45,.38)},chest_roll=-8.)),(6,pose(crouch=.18,pitch=10.,hands={'f':(.10,.39,.44),'b':(-.10,.40,.42)})),(9,guard)])
    def guard_variation(front_y=0.,front_z=0.,back_y=0.,back_z=0.):
        return {'f':add(fguard,(0.,front_y,front_z)), 'b':add(bguard,(0.,back_y,back_z))}
    auxiliary('idle',[(0,guard),(9,pose(crouch=.105 if rig.role=='player' else .092,pitch=4.,yaw=-12.,hands=guard_variation(.01,.01,.01,.01))),(18,pose(crouch=.13 if rig.role=='player' else .115,pitch=6.,yaw=-8.,hands=guard_variation(-.01,-.01,-.01,-.01))),(27,pose(crouch=.105 if rig.role=='player' else .092,pitch=4.,yaw=-12.)),(35,guard)],36)
    auxiliary('walk',[(0,guard),(8,pose(crouch=.095 if rig.role=='player' else .08,pitch=8.,yaw=-14.,feet={'f':(.16,.10,.40),'b':(-.16,0.,-.22)},hands=guard_variation(-.015,-.025,.015,.025))),(17,pose(crouch=.14 if rig.role=='player' else .12,pitch=6.,yaw=-7.)),(26,pose(crouch=.095 if rig.role=='player' else .08,pitch=8.,yaw=-6.,feet={'f':(.16,0.,.24),'b':(-.16,.10,-.02)},hands=guard_variation(.015,.025,-.015,-.025))),(35,guard)],36)
    collapse_poles = {'f':(.9,-.65,.05),'b':(-.9,-.65,.05)}
    down = pose(crouch=rig.height-.23,pitch=91.,yaw=12.,lean=-9.,chest_pitch=7.,hands={'f':(.35,-.05,.39),'b':(-.30,-.05,.30)},feet={'f':(.20,.015,-.42),'b':(-.20,0.,-.24)},rolls={'f':0.,'b':0.},arm_poles=collapse_poles)
    auxiliary('ko',[(0,heavy_impact),(7,pose(crouch=.39,pitch=-42.,yaw=26.,lean=-25.,hands={'f':(.43,-.08,.26),'b':(-.43,-.12,.24)})),
                    (11,pose(crouch=(.39+rig.height-.33)*.5,pitch=14.,yaw=22.,lean=-18.,hands={'f':(.40,-.075,.34),'b':(-.38,-.095,.28)},feet={'f':(.18,.015,-.06),'b':(-.18,0.,-.23)})),
                    (15,pose(crouch=rig.height-.33,pitch=70.,yaw=18.,lean=-12.,hands={'f':(.37,-.07,.42),'b':(-.33,-.07,.32)},feet={'f':(.20,.03,-.36),'b':(-.20,0.,-.24)},rolls={'f':0.,'b':0.},arm_poles=collapse_poles)),(21,pose(crouch=rig.height-.20,pitch=99.,yaw=10.,lean=-11.,hands={'f':(.35,-.05,.39),'b':(-.30,-.05,.30)},feet={'f':(.20,.015,-.42),'b':(-.20,0.,-.24)},rolls={'f':0.,'b':0.},arm_poles=collapse_poles)),(27,down)],28)
    for clip in clips.values(): dense_targets(rig,clip)
    return clips

def main():
    measured = json.loads((HERE/'reports/rig-rest.json').read_text(encoding='utf-8-sig'))
    splits = timing()
    roles = {}
    for role in ['player','foe']:
        source = json.loads((HERE/('project/data/motion_input.json' if role=='player' else 'project/data/motion_input_foe.json')).read_text(encoding='utf-8-sig'))
        rig = Rig(role,measured['roles'][role],source)
        roles[role] = {'clips':build(rig,splits)}
        print(role, 'clips',len(roles[role]['clips']), 'max unreachable target',round(rig.max_ik_error,5),'max actual sole solve error',round(rig.max_sole_error,6))
    data = {'version':1,'coordinate_system':'godot_y_up_z_forward','bones':BONES,'roles':roles,
            'authoring':{'rig_source':'reports/rig-rest.json','leaf_tail_source':'motion_input*.json apose_points',
                         'method':'C1 monotone target-space Hermite sampled every half-frame; analytic two-bone IK, measured rest-relative 3D orientations; exact weighted-boot sole floor calibration per sample',
                         'sample_step_frames':.5,
                         'floor_y':0.0,'support_policy':'stationary both boots; sweep rear boot; walk alternates after frame17'}}
    (HERE/'project/data/combat_motion_3d.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__': main()
