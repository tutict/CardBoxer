"""Byte-preservation and actual GLB linear-blend deformation checks.

Reads the native combat keys with q_rest * q_delta, includes inverse bind
matrices and the neutral root, and never resizes or rewrites a GLB.
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DTYPES = {5121: 'u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
WIDTHS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}


class GLB:
    def __init__(self, path):
        self.path = Path(path)
        self.raw = self.path.read_bytes()
        magic, version, length = struct.unpack_from('<III', self.raw)
        assert magic == 0x46546C67 and version == 2 and length == len(self.raw)
        json_len, json_kind = struct.unpack_from('<II', self.raw, 12)
        assert json_kind == 0x4E4F534A
        self.doc = json.loads(self.raw[20:20 + json_len])
        self.bin_start = 28 + json_len
        bin_len, bin_kind = struct.unpack_from('<II', self.raw, 20 + json_len)
        assert bin_kind == 0x004E4942 and self.bin_start + bin_len == len(self.raw)
        self.primitive = self.doc['meshes'][0]['primitives'][0]
        assert len(self.doc['meshes']) == 1 and len(self.doc['meshes'][0]['primitives']) == 1
        self.skin = self.doc['skins'][0]
        self.names = [self.doc['nodes'][n]['name'] for n in self.skin['joints']]
        self.positions = self.array(self.primitive['attributes']['POSITION']).astype(float)
        self.indices = self.array(self.primitive['indices']).reshape(-1, 3).astype(int)
        self.joints = self.array(self.primitive['attributes']['JOINTS_0']).astype(int)
        self.weights = self.array(self.primitive['attributes']['WEIGHTS_0']).astype(float)
        self.bind = self.array(self.skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1).astype(float)
        self.dense = np.zeros((len(self.positions), len(self.names)))
        np.add.at(self.dense, (np.arange(len(self.positions))[:, None], self.joints), self.weights)
        self.parents = {c: i for i, n in enumerate(self.doc['nodes']) for c in n.get('children', [])}

    def layout(self, accessor):
        a = self.doc['accessors'][accessor]
        v = self.doc['bufferViews'][a['bufferView']]
        dtype = np.dtype(DTYPES[a['componentType']])
        width = WIDTHS[a['type']]
        offset = self.bin_start + v.get('byteOffset', 0) + a.get('byteOffset', 0)
        stride = v.get('byteStride', width * dtype.itemsize)
        assert 'sparse' not in a and not a.get('normalized', False)
        return a['count'], width, dtype, offset, stride

    def array(self, accessor):
        count, width, dtype, offset, stride = self.layout(accessor)
        return np.ndarray((count, width), dtype=dtype, buffer=self.raw, offset=offset,
                          strides=(stride, dtype.itemsize)).copy()

    def allowed_byte_mask(self):
        mask = np.zeros(len(self.raw), dtype=bool)
        for name in ['JOINTS_0', 'WEIGHTS_0']:
            count, width, dtype, offset, stride = self.layout(self.primitive['attributes'][name])
            for row in range(count):
                mask[offset + row * stride:offset + row * stride + width * dtype.itemsize] = True
        return mask

    def matrices(self, key=None):
        pending = list(range(len(self.doc['nodes'])))
        glob = {}
        while pending:
            for index in pending[:]:
                parent = self.parents.get(index)
                if parent is not None and parent not in glob:
                    continue
                node = self.doc['nodes'][index]
                q = np.asarray(node.get('rotation', [0, 0, 0, 1]), float)
                if key and node.get('name') in key['rotations']:
                    q = qm(q, np.asarray(key['rotations'][node['name']]))
                local = np.eye(4)
                local[:3, :3] = rotation(q) @ np.diag(node.get('scale', [1, 1, 1]))
                local[:3, 3] = node.get('translation', [0, 0, 0])
                if key and node.get('name') == 'hips':
                    local[:3, 3] += key.get('root_offset', [0, 0, 0])
                if 'matrix' in node:
                    assert not key or node.get('name') not in key['rotations']
                    local = np.asarray(node['matrix']).reshape(4, 4).T
                glob[index] = glob.get(parent, np.eye(4)) @ local
                pending.remove(index)
        return np.asarray([glob[n] for n in self.skin['joints']]) @ self.bind

    def deform(self, key=None, dense=None):
        matrices = self.matrices(key)
        p4 = np.column_stack((self.positions, np.ones(len(self.positions))))
        transformed = np.einsum('bij,nj->nbi', matrices[:, :3, :], p4)
        return np.einsum('nb,nbi->ni', self.dense if dense is None else dense, transformed)


def qm(a, b):
    return np.r_[a[3] * b[:3] + b[3] * a[:3] + np.cross(a[:3], b[:3]),
                 a[3] * b[3] - np.dot(a[:3], b[:3])]


def rotation(q):
    x, y, z, w = q / np.linalg.norm(q)
    return np.array([[1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
                     [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
                     [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)]])


def components(glb):
    parents = np.arange(len(glb.positions))
    def find(n):
        while parents[n] != n:
            parents[n] = parents[parents[n]]
            n = parents[n]
        return n
    for triangle in glb.indices:
        a, b, c = [find(int(x)) for x in triangle]
        parents[b] = a
        parents[c] = a
    return np.array([find(i) for i in range(len(parents))])


def position_groups(glb):
    # Exact exported duplicate positions, including UV/normal splits.
    return np.unique(glb.positions, axis=0, return_inverse=True)[1]


def deformation_metrics(glb, clips, dense=None, details=False):
    edges = np.unique(np.sort(np.vstack([glb.indices[:, [0, 1]], glb.indices[:, [1, 2]],
                                       glb.indices[:, [2, 0]]]), axis=1), axis=0)
    rest_len = np.linalg.norm(glb.positions[edges[:, 0]] - glb.positions[edges[:, 1]], axis=1)
    # Tiny source tessellation is excluded from ratio counts, but its absolute
    # stretch is still measured. This prevents epsilon-sized edges dominating.
    useful = rest_len >= .005
    records = []
    maxima = []
    worst_detail = []
    for clip, value in clips.items():
        for key in value['keys']:
            deformed = glb.deform(key, dense)
            length = np.linalg.norm(deformed[edges[:, 0]] - deformed[edges[:, 1]], axis=1)
            ratio = length / np.maximum(rest_len, 1e-8)
            excess = length - rest_len
            records.append({'clip': clip, 'frame': key['frame'],
                            'edges_over_4x': int(np.count_nonzero(useful & (ratio > 4))),
                            'edges_over_10cm_excess': int(np.count_nonzero(excess > .10)),
                            'max_edge_excess_m': float(excess.max()),
                            'max_useful_edge_ratio': float(ratio[useful].max())})
            maxima.append(excess)
            if details and clip in ['cross', 'sweep'] and key['frame'] == value['contact_frame']:
                for n in np.argsort(excess)[-12:][::-1]:
                    a, b = edges[n]
                    worst_detail.append({'clip': clip, 'frame': key['frame'], 'vertices': [int(a), int(b)],
                                         'rest_positions': glb.positions[[a, b]].tolist(),
                                         'dominant_bones': [glb.names[int(glb.dense[v].argmax())] for v in [a, b]],
                                         'weight_vectors': glb.dense[[a, b]].round(4).tolist(),
                                         'excess_m': float(excess[n]), 'ratio': float(ratio[n])})
    all_excess = np.max(maxima, axis=0)
    return {'samples': records, 'distinct_edges_over_10cm_excess': int(np.count_nonzero(all_excess > .10)),
            'max_edge_excess_m': float(all_excess.max()), 'worst_contact_edges': worst_detail}


def preservation(before, after):
    assert len(before.raw) == len(after.raw), 'GLB length changed'
    assert before.doc == after.doc, 'GLB JSON metadata changed'
    a = np.frombuffer(before.raw, dtype='u1')
    b = np.frombuffer(after.raw, dtype='u1')
    allowed = before.allowed_byte_mask()
    assert np.array_equal(a[~allowed], b[~allowed]), 'Bytes outside JOINTS_0/WEIGHTS_0 changed'
    assert np.all(after.weights >= 0) and np.all(np.isfinite(after.weights))
    assert np.max(np.abs(after.weights.sum(axis=1) - 1)) < 2e-6, 'Weights not normalized'
    assert np.max(after.joints) < len(after.names), 'Joint index outside skin'
    assert np.max(np.linalg.norm(after.deform() - after.positions, axis=1)) < 3e-6, 'Bind/rest deformation changed'
    return {'bytes_outside_skin_preserved': True, 'json_preserved': True,
            'changed_vertices': int(np.count_nonzero(np.max(np.abs(before.dense - after.dense), axis=1) > 1e-7)),
            'changed_bytes': int(np.count_nonzero(a != b)),
            'rest_max_error_m': float(np.max(np.linalg.norm(after.deform() - after.positions, axis=1))),
            'sha256_before': hashlib.sha256(before.raw).hexdigest(),
            'sha256_after': hashlib.sha256(after.raw).hexdigest()}


def inspect(glb):
    comp = components(glb)
    groups = position_groups(glb)
    gmin = np.full((groups.max() + 1, len(glb.names)), np.inf)
    gmax = np.full_like(gmin, -np.inf)
    np.minimum.at(gmin, groups, glb.dense)
    np.maximum.at(gmax, groups, glb.dense)
    mismatched = np.max(gmax - gmin, axis=1) > 1e-5
    return {'vertices': len(glb.positions), 'triangles': len(glb.indices),
            'components': len(np.unique(comp)), 'coincident_groups': len(np.unique(groups)),
            'coincident_weight_disagreement_groups': int(mismatched.sum()),
            'bones': glb.names, 'dominant_counts': {n: int((glb.dense.argmax(axis=1) == i).sum()) for i, n in enumerate(glb.names)},
            'weight_sum_max_error': float(np.abs(glb.weights.sum(axis=1) - 1).max()),
            'rest_max_error_m': float(np.linalg.norm(glb.deform() - glb.positions, axis=1).max())}


def check_imported_godot(executable):
    before = json.loads((ROOT / 'reports/rig-rest.json').read_text(encoding='utf-8'))
    output = ROOT / 'logs/skin-imported-rest.json'
    env = os.environ.copy()
    env['NATIVE_RIG_OUT'] = str(output)
    command = [str(executable), '--headless', '--path', str(ROOT / 'project'),
               '--log-file', str(ROOT / 'logs/skin-import-check-engine.log'),
               '--script', str(ROOT / 'tools/rig_rest_probe.gd')]
    result = subprocess.run(command, env=env, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=55,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'SCRIPT ERROR:' not in result.stderr, result.stderr
    after = json.loads(output.read_text(encoding='utf-8'))
    summary = {}
    for role in ['player', 'foe']:
        original = before['roles'][role]
        imported = after['roles'][role]
        assert len(imported['bones']) == 14, f'{role}: imported bone count changed'
        assert [b['name'] for b in original['bones']] == [b['name'] for b in imported['bones']], f'{role}: imported bone names changed'
        for a, b in zip(original['bones'], imported['bones']):
            for field in ['parent', 'parent_index', 'local_rest', 'global_rest', 'initial_pose']:
                assert a[field] == b[field], f'{role}/{a["name"]}: imported {field} changed'
        for field in ['model_transform', 'skeleton_transform']:
            assert original[field] == imported[field], f'{role}: imported {field} changed'
        summary[role] = {'bone_count': 14, 'names_parents_and_rests_preserved': True,
                         'neutral_bone_rest_preserved': True,
                         'log': str(ROOT / 'logs/skin-import-check-engine.log')}
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--json', type=Path)
    parser.add_argument('--godot', type=Path, help='Verify cached Godot bone names/rest after reimport')
    args = parser.parse_args()
    motion = json.loads((ROOT / 'project/data/combat_motion_3d.json').read_text(encoding='utf-8'))
    report = {}
    for role in ['player', 'foe']:
        base = GLB(ROOT / 'baseline/assets/3d' / f'{role}-rigged.glb')
        current = GLB(ROOT / 'project/assets/3d' / f'{role}-rigged.glb')
        clips = motion['roles'][role]['clips']
        report[role] = {'inspection': inspect(current), 'preservation': preservation(base, current),
                        'before': deformation_metrics(base, clips, details=args.inspect),
                        'after': deformation_metrics(current, clips, details=args.inspect)}
        if args.verify:
            assert np.max(current.dense[:, current.names.index('neutral_bone')]) == 0, f'{role}: neutral vertices still pin moving triangles'
            original_neutral = base.dense[:, base.names.index('neutral_bone')] > .5
            assert np.array_equal(base.joints[~original_neutral], current.joints[~original_neutral]), f'{role}: joint repair exceeded original neutral outliers'
            assert np.array_equal(base.weights[~original_neutral], current.weights[~original_neutral]), f'{role}: weight repair exceeded original neutral outliers'
            if role == 'player':
                allowed = [current.names.index('head'), current.names.index('neck')]
                assert np.max(np.delete(current.dense[original_neutral], allowed, axis=1)) == 0, 'Head-ribbon outliers retained limb influence'
            assert report[role]['inspection']['coincident_weight_disagreement_groups'] == 0, f'{role}: repair split coincident seam weights'
            assert report[role]['after']['distinct_edges_over_10cm_excess'] < report[role]['before']['distinct_edges_over_10cm_excess'], f'{role}: large deformation defects did not improve'
            assert report[role]['after']['max_edge_excess_m'] < report[role]['before']['max_edge_excess_m'], f'{role}: worst deformation did not improve'
    if args.godot:
        imported = check_imported_godot(args.godot)
        for role in ['player', 'foe']:
            report[role]['imported_godot'] = imported[role]
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
