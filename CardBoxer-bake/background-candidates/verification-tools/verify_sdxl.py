"""Verify the downloaded SDXL checkpoint is a complete, readable safetensors file.

Size alone is not proof: a truncated file can still have the right byte count
only by accident, and a corrupt header would fail at ComfyUI load time. This
parses the header and checks that the last tensor's data end equals the file end.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

PATH = Path(r"D:\Comfy-Desktop\ComfyUI-Shared\models\checkpoints\sd_xl_base_1.0.safetensors")
EXPECTED_SIZE = 6_938_078_334


def main() -> int:
    if not PATH.exists():
        print(f"MISSING: {PATH}")
        return 1
    size = PATH.stat().st_size
    print(f"size: {size} (expected {EXPECTED_SIZE})")
    if size != EXPECTED_SIZE:
        print("SIZE MISMATCH")
        return 1
    with PATH.open("rb") as handle:
        header_len = struct.unpack("<Q", handle.read(8))[0]
        header = json.loads(handle.read(header_len))
    tensors = {k: v for k, v in header.items() if k != "__metadata__"}
    data_end = max(v["data_offsets"][1] for v in tensors.values())
    computed_end = 8 + header_len + data_end
    print(f"header_len: {header_len}; tensors: {len(tensors)}")
    print(f"last tensor data end: {computed_end}; file size: {size}")
    for key in ("model.diffusion_model.input_blocks.0.0.weight", "first_stage_model.encoder.conv_in.weight"):
        if key in tensors:
            print(f"sample tensor: {key} dtype={tensors[key]['dtype']} shape={tensors[key]['shape']}")
    if computed_end != size:
        print("TRUNCATED OR CORRUPT: tensor data does not end at EOF")
        return 1
    if not any("conditioner" in k or "cond_stage_model" in k for k in tensors):
        print("NOTE: no text-encoder keys found (unexpected for an all-in-one checkpoint)")
    print("SAFETENSORS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
