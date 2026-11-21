"""Check actual canonical skin/morph geometry over every unchanged authored key."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

TASK = Path(__file__).resolve().parent.parent
SKIN_HELPER = TASK.parent / "动作修正-原生3D/tools/check_native_skin.py"
module_spec = importlib.util.spec_from_file_location("retopo_original_skin_reader", SKIN_HELPER)
skin = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(skin)
TARGETS = ("grip_half_f", "grip_f", "grip_half_b", "grip_b")


class Mesh(skin.GLB):
    def __init__(self, path: Path):
        super().__init__(path)
        names = self.doc["meshes"][0].get("extras", {}).get("targetNames", [])
        self.morphs = {}
        for name, target in zip(names, self.primitive.get("targets", [])):
            self.morphs[name] = self.array(target["POSITION"]).astype(float)
        self.edges = np.unique(np.sort(np.vstack((self.indices[:, [0, 1]],
                                                 self.indices[:, [1, 2]],
                                                 self.indices[:, [2, 0]])), axis=1), axis=0)
        self.edge_lengths = np.linalg.norm(self.positions[self.edges[:, 0]] - self.positions[self.edges[:, 1]], axis=1)
        shin = self.dense[:, self.names.index("shin_f")] + self.dense[:, self.names.index("shin_b")]
        self.boots = np.flatnonzero((self.positions[:, 1] < .24) & (shin > .65))
        if self.boots.size == 0:
            raise AssertionError("Boot support surface disappeared")

    def points(self, key: dict | None = None) -> np.ndarray:
        points = self.positions.copy()
        if key:
            for side, amount in zip(("f", "b"), key.get("hand_grip", [0, 0])):
                half = 2 * amount if amount <= .5 else 2 * (1 - amount)
                closed = 0 if amount <= .5 else 2 * amount - 1
                for name, weight in (("grip_half_" + side, half), ("grip_" + side, closed)):
                    if name in self.morphs:
                        points += self.morphs[name] * weight
        points = np.column_stack((points, np.ones(points.shape[0])))
        matrices = self.matrices(key)
        output = np.zeros((points.shape[0], 3))
        for slot in range(4):
            transformed = np.einsum("nij,nj->ni", matrices[self.joints[:, slot], :3, :], points)
            output += transformed * self.weights[:, slot, None]
        return output

    def measures(self, points: np.ndarray) -> dict:
        lengths = np.linalg.norm(points[self.edges[:, 0]] - points[self.edges[:, 1]], axis=1)
        excess = lengths - self.edge_lengths
        return {"finite": bool(np.isfinite(points).all()),
                "sole_m": float(points[self.boots, 1].min()),
                "max_edge_excess_m": float(excess.max()),
                "edges_over_10cm_excess": int(np.count_nonzero(excess > .10)),
                "bounds_min": points.min(axis=0).tolist(), "bounds_max": points.max(axis=0).tolist()}


def duplicate_span(groups: np.ndarray, values: np.ndarray) -> float:
    count = int(groups.max()) + 1
    low = np.full((count, values.shape[1]), np.inf)
    high = np.full_like(low, -np.inf)
    np.minimum.at(low, groups, values)
    np.maximum.at(high, groups, values)
    return float(np.max(high - low))


def check_role(role: str, clips: dict) -> dict:
    source = Mesh(TASK / "baseline/assets/3d" / (role + "-rigged.glb"))
    candidate = Mesh(TASK / "project/assets/3d" / (role + "-rigged.glb"))
    failures = []
    if set(candidate.morphs) != set(TARGETS):
        failures.append("Four actual progressive hand geometry targets missing")
    if candidate.names != source.names:
        failures.append("Canonical skin joint names/order changed")
    rest_error = float(np.linalg.norm(candidate.points() - candidate.positions, axis=1).max())
    if rest_error > 1e-5:
        failures.append("Canonical rest/IBM drift")
    _, groups = np.unique(candidate.positions, axis=0, return_inverse=True)
    weight_span = duplicate_span(groups, candidate.dense)
    morph_span = max((duplicate_span(groups, delta) for delta in candidate.morphs.values()), default=0.0)
    if weight_span > 2e-5 or morph_span > 2e-5:
        failures.append("Coincident UV/normal seam vertices diverge in skin or morph geometry")
    records = []
    max_sole = 0.0
    max_regression = 0.0
    for name, clip in clips.items():
        for key in clip["keys"]:
            before = source.measures(source.points(key))
            after = candidate.measures(candidate.points(key))
            sole_error = abs(after["sole_m"] - before["sole_m"])
            regression = after["max_edge_excess_m"] - before["max_edge_excess_m"]
            max_sole = max(max_sole, sole_error)
            max_regression = max(max_regression, regression)
            if not after["finite"]:
                failures.append(f"{name} frame {key['frame']}: nonfinite skinned geometry")
            if sole_error > .02:
                failures.append(f"{name} frame {key['frame']}: sole error {sole_error:.6f}m exceeds .02m")
            if regression > .02:
                failures.append(f"{name} frame {key['frame']}: edge-stretch regression {regression:.6f}m")
            records.append({"clip": name, "frame": key["frame"], "hand_grip": key.get("hand_grip"),
                            "sole_error_m": sole_error, "edge_excess_regression_m": regression,
                            "source": before, "candidate": after})
        print(f"FULL_BODY {role} {name}: {len(clip['keys'])} actual skin/morph keys", flush=True)
    return {"ok": not failures, "failures": failures, "clips": list(clips), "authored_keys": len(records),
            "triangles": len(candidate.indices), "vertices": len(candidate.positions),
            "candidate_sha256": hashlib.sha256(candidate.raw).hexdigest(),
            "source_sha256": hashlib.sha256(source.raw).hexdigest(), "rest_error_m": rest_error,
            "seam_weight_span": weight_span, "seam_morph_span_m": morph_span,
            "sole_error_max_m": max_sole, "edge_excess_regression_max_m": max_regression,
            "records": records}


def main() -> None:
    data = json.loads((TASK / "project/data/combat_motion_3d.json").read_text(encoding="utf-8"))
    roles = {role: check_role(role, data["roles"][role]["clips"]) for role in ("player", "foe")}
    result = {"ok": all(value["ok"] for value in roles.values()), "roles": roles,
              "scope": "All authored body keys with actual progressive morphs and canonical IBMs. Facing rotates the model rigidly and preserves distances; actual both-facing render coverage is recorded separately. Edge excess is compared to the immutable source, whose cloth already contains stretched edges."}
    (TASK / "reports/full-body-geometry.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for role, row in roles.items():
        for failure in row["failures"][:12]:
            print("FAIL: " + role + " " + failure)
        print(f"{role}: {'PASS' if row['ok'] else 'FAIL'} sole_max={row['sole_error_max_m']:.6f}m, keys={row['authored_keys']}")
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
