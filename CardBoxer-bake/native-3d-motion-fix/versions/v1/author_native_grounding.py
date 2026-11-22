"""Read-only boot skin measurements for native pose floor calibration."""
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE/'tools'))
from check_native_skin import GLB

def boot_masks(glb):
    masks = {}
    for suffix in ['f','b']:
        shin = glb.names.index('shin_'+suffix)
        mask = (glb.dense[:,shin] > .65) & (glb.positions[:,1] < .24)
        assert mask.sum() > 50, 'Boot vertex classification unexpectedly empty'
        masks[suffix] = mask
    return masks

class BootGrounder:
    def __init__(self, role):
        self.glb = GLB(HERE/'project/assets/3d'/f'{role}-rigged.glb')
        self.masks = boot_masks(self.glb)
        self.boots = {}
        for suffix, mask in self.masks.items():
            self.boots[suffix] = (np.column_stack((self.glb.positions[mask],np.ones(mask.sum()))),self.glb.dense[mask])

    def sole(self, pose, suffix):
        matrices = self.glb.matrices(pose)
        positions,weights = self.boots[suffix]
        heights = np.einsum('bj,nj->nb', matrices[:,1,:],positions)
        return float(np.einsum('nb,nb->n',weights,heights).min())

    def sole_pair(self,pose):
        return {s:self.sole(pose,s) for s in ['f','b']}
