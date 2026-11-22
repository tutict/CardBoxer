"""Bounded GLB skin repair. Dry run by default; --write changes skin bytes only.

The baseline GLBs are immutable rollback copies. Unweighted neutral outliers
inherit the surrounding surface's weights through exact-position welded mesh
adjacency, rather than being assigned by proximity to a different body part.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from check_native_skin import ROOT, GLB, deformation_metrics, position_groups, preservation


def repair(glb):
    groups = position_groups(glb)
    size = int(groups.max()) + 1
    position = np.zeros((size, 3))
    position[groups] = glb.positions
    dense = np.zeros((size, len(glb.names)))
    dense[groups] = glb.dense
    donor_dense = dense.copy()
    neutral = glb.names.index('neutral_bone')
    target = np.flatnonzero(dense[:, neutral] > .5)
    triangles = groups[glb.indices]
    adjacency = [set() for _ in range(size)]
    for a, b, c in triangles:
        adjacency[a].update([int(b), int(c)])
        adjacency[b].update([int(a), int(c)])
        adjacency[c].update([int(a), int(b)])
    for vertex in target:
        visited = {int(vertex)}
        frontier = {int(vertex)}
        donors = set()
        # Search the same connected surface, including normal/UV splits.
        for _ in range(12):
            frontier = set().union(*(adjacency[n] for n in frontier)) - visited
            visited.update(frontier)
            donors.update(n for n in frontier if donor_dense[n, neutral] < 1e-6)
            if len(donors) >= 3:
                break
        assert donors, f'Neutral vertex {vertex} has no local weighted surface'
        donors = np.array(sorted(donors))
        distances = np.linalg.norm(position[donors] - position[vertex], axis=1)
        # The support is bounded to the local missing-weight cluster, excluding
        # distant parts of a long ribbon/cape from the donor interpolation.
        keep = distances <= max(.025, float(distances.min()) * 2.5)
        donors, distances = donors[keep], distances[keep]
        weight = (donor_dense[donors] / np.maximum(distances[:, None], .001)).sum(axis=0)
        weight[neutral] = 0
        # High ribbon fragments sit above the neck joint. Their donor surface
        # carries a small legacy arm influence; restrict only these repaired
        # outliers to the existing head/neck chain so punches cannot drag them.
        head = glb.names.index('head')
        head_height = np.linalg.inv(glb.bind[head])[1, 3]
        if position[vertex, 1] > head_height - .05:
            anatomical = np.zeros_like(weight)
            anatomical[[head, glb.names.index('neck')]] = weight[[head, glb.names.index('neck')]]
            assert anatomical.sum() > .5 * weight.sum(), 'High outlier not supported by head/neck'
            weight = anatomical
        strongest = np.argsort(weight)[-4:]
        dense[vertex] = 0
        dense[vertex, strongest] = weight[strongest] / weight[strongest].sum()
    repaired = dense[groups]
    changed = np.flatnonzero(np.max(np.abs(repaired - glb.dense), axis=1) > 1e-7)
    assert len(changed) <= 64, 'Repair exceeded its documented neutral-outlier bound'
    assert np.max(repaired[:, neutral]) == 0, 'Moving surface remains on neutral bone'
    raw = bytearray(glb.raw)
    for semantic in ['JOINTS_0', 'WEIGHTS_0']:
        count, width, dtype, offset, stride = glb.layout(glb.primitive['attributes'][semantic])
        assert width == 4
        for vertex in changed:
            ids = np.argsort(-repaired[vertex], kind='stable')[:4]
            weights = repaired[vertex, ids]
            value = ids if semantic == 'JOINTS_0' else weights / weights.sum()
            data = value.astype(dtype).tobytes()
            start = offset + int(vertex) * stride
            raw[start:start + len(data)] = data
    return bytes(raw), repaired, {'neutral_vertices_before': int((glb.dense[:, neutral] > .5).sum()),
                                  'neutral_position_groups_before': len(target),
                                  'changed_vertices': len(changed)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    motion = json.loads((ROOT / 'project/data/combat_motion_3d.json').read_text(encoding='utf-8'))
    summary = {}
    for role in ['player', 'foe']:
        baseline = GLB(ROOT / 'baseline/assets/3d' / f'{role}-rigged.glb')
        destination = ROOT / 'project/assets/3d' / f'{role}-rigged.glb'
        current = GLB(destination)
        # Reproducible and idempotent: derive from the preserved baseline, never
        # repair a previous repair and accumulate weight drift.
        raw, dense, changes = repair(baseline)
        clips = motion['roles'][role]['clips']
        before = deformation_metrics(baseline, clips)
        after = deformation_metrics(baseline, clips, dense=dense)
        summary[role] = {'changes': changes, 'before': before, 'after': after}
        assert after['max_edge_excess_m'] < before['max_edge_excess_m']
        assert after['distinct_edges_over_10cm_excess'] < before['distinct_edges_over_10cm_excess']
        if args.write:
            preservation(baseline, current)
            target = baseline.dense[:, baseline.names.index('neutral_bone')] > .5
            assert np.array_equal(current.joints[~target], baseline.joints[~target]), 'Destination has unrelated joint edits'
            assert np.array_equal(current.weights[~target], baseline.weights[~target]), 'Destination has unrelated weight edits'
            destination.write_bytes(raw)
            summary[role]['preservation'] = preservation(baseline, GLB(destination))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
