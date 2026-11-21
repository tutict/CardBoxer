"""Fetch Blender 5.2.3 LTS portable zip from official mirrors, chunked in parallel.

Why this exists:
  download.blender.org is behind a Cloudflare "Just a moment..." challenge here,
  and `winget download` fails with 0x80190193 (403). Official mirrors serve the
  same bytes with Range support, but each single connection is ~300 KB/s, so we
  split the file into chunks and pull them from several mirrors concurrently.

  The expected sha256 comes from the mirrors' own blender-5.2.3.sha256 manifest
  and is cross-checked against the winget package manifest (for the MSI sibling).
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import os
import sys
import time
import urllib.request

FILE = "blender-5.2.3-windows-x64.zip"
SIZE = 405_839_452
EXPECTED = "723f08a4401502561eb763cdeacf8745b31e5f3f154d287d3830d97cf75dc2fb"
MIRRORS = [
    "https://mirror.freedif.org/blender/release/Blender5.2",
    "https://mirrors.ocf.berkeley.edu/blender/release/Blender5.2",
    "https://mirror.clarkson.edu/blender/release/Blender5.2",
    "https://ftp.halifax.rwth-aachen.de/blender/release/Blender5.2",
]
CHUNKS = 12
PART_DIR = r"C:\Users\tutic\AppData\Local\Temp\blender-upgrade\parts"
OUT = r"D:\Tools\Blender-5.2.3\blender-5.2.3-windows-x64.zip"


def part_path(i: int) -> str:
    return os.path.join(PART_DIR, f"part_{i:02d}")


def chunk_span(i: int) -> tuple[int, int]:
    step = SIZE // CHUNKS
    start = i * step
    end = SIZE - 1 if i == CHUNKS - 1 else (i + 1) * step - 1
    return start, end


def probe() -> None:
    start, end = 0, 1023
    req = urllib.request.Request(
        MIRRORS[0] + "/" + FILE,
        headers={"Range": f"bytes={start}-{end}", "User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    print(f"PROBE_OK status={resp.status} bytes={len(data)}", flush=True)


def fetch(i: int) -> tuple[int, int]:
    start, end = chunk_span(i)
    path = part_path(i)
    want = end - start + 1
    if os.path.exists(path) and os.path.getsize(path) == want:
        return i, want  # resumable
    last_error: Exception | None = None
    for attempt in range(6):
        # Every chunk starts from the fastest mirror. The earlier version rotated
        # by chunk index, which sent 3/4 of the chunks to 40-60 KB/s mirrors and
        # made them sit through two 120 s SSL timeouts before reaching a fast one.
        url = MIRRORS[attempt % len(MIRRORS)] + "/" + FILE
        req = urllib.request.Request(
            url,
            headers={"Range": f"bytes={start}-{end}", "User-Agent": "Mozilla/5.0"},
        )
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = resp.read()
            if len(data) != want:
                raise ValueError(f"short read {len(data)} != {want}")
            tmp = path + ".tmp"
            with open(tmp, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
            dt = time.time() - t0
            print(f"chunk {i:02d} OK {len(data)} B in {dt:.1f}s via {url.split('/')[2]}", flush=True)
            return i, len(data)
        except Exception as exc:  # noqa: BLE001 - retry across mirrors
            last_error = exc
            print(f"chunk {i:02d} attempt {attempt + 1} failed: {exc}", flush=True)
            time.sleep(2)
    raise RuntimeError(f"chunk {i} exhausted retries: {last_error}")


def main() -> int:
    os.makedirs(PART_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "probe":
        probe()
        return 0

    if os.path.exists(OUT) and os.path.getsize(OUT) == SIZE:
        print("zip already present, verifying", flush=True)
    else:
        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=CHUNKS) as pool:
            results = list(pool.map(fetch, range(CHUNKS)))
        total = sum(n for _, n in results)
        if total != SIZE:
            print(f"FATAL chunk total {total} != {SIZE}", flush=True)
            return 1
        print(f"all {CHUNKS} chunks ready in {time.time() - t0:.1f}s, joining", flush=True)
        tmp = OUT + ".joining"
        with open(tmp, "wb") as sink:
            for i in range(CHUNKS):
                with open(part_path(i), "rb") as src:
                    while True:
                        block = src.read(1 << 20)
                        if not block:
                            break
                        sink.write(block)
        os.replace(tmp, OUT)

    digest = hashlib.sha256()
    with open(OUT, "rb") as handle:
        while True:
            block = handle.read(1 << 20)
            if not block:
                break
            digest.update(block)
    got = digest.hexdigest()
    size = os.path.getsize(OUT)
    print(f"size={size} (expected {SIZE})", flush=True)
    print(f"sha256={got}", flush=True)
    print(f"expected={EXPECTED}", flush=True)
    if size != SIZE or got != EXPECTED:
        print("FATAL sha256/size mismatch", flush=True)
        return 1
    print("DOWNLOAD_OK", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
