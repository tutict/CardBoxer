"""Fetch the last missing 33.8 MB chunk as six small parallel sub-ranges.

A single long-lived 33 MB TLS connection kept getting killed (SIGTERM / SSL
handshake timeout). Small ranges finish in seconds and can retry independently.
"""

from __future__ import annotations

import concurrent.futures
import os
import time
import urllib.request

FILE = "blender-5.2.3-windows-x64.zip"
MIRRORS = [
    "https://mirror.freedif.org/blender/release/Blender5.2",
    "https://mirrors.ocf.berkeley.edu/blender/release/Blender5.2",
    "https://mirror.clarkson.edu/blender/release/Blender5.2",
    "https://ftp.halifax.rwth-aachen.de/blender/release/Blender5.2",
]
START, END = 101_459_862, 135_279_815  # chunk 03 inclusive byte range
WANT = END - START + 1
SUBS = 6
DIR = r"C:\Users\tutic\AppData\Local\Temp\blender-upgrade\parts"
SUB_DIR = os.path.join(DIR, "sub03")
OUT = os.path.join(DIR, "part_03")


def span(i: int) -> tuple[int, int]:
    step = WANT // SUBS
    a = START + i * step
    b = END if i == SUBS - 1 else START + (i + 1) * step - 1
    return a, b


def fetch(i: int) -> int:
    a, b = span(i)
    want = b - a + 1
    path = os.path.join(SUB_DIR, f"sub_{i:02d}")
    if os.path.exists(path) and os.path.getsize(path) == want:
        return want
    for attempt in range(12):
        url = MIRRORS[(i + attempt) % len(MIRRORS)] + "/" + FILE
        req = urllib.request.Request(
            url, headers={"Range": f"bytes={a}-{b}", "User-Agent": "Mozilla/5.0"}
        )
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()
            if len(data) != want:
                raise ValueError(f"short read {len(data)} != {want}")
            tmp = path + ".tmp"
            with open(tmp, "wb") as handle:
                handle.write(data)
            os.replace(tmp, path)
            print(f"sub {i:02d} OK {len(data)}B {time.time() - t0:.1f}s via {url.split('/')[2]}", flush=True)
            return want
        except Exception as exc:  # noqa: BLE001
            print(f"sub {i:02d} attempt {attempt + 1}: {exc}", flush=True)
            time.sleep(1)
    raise RuntimeError(f"sub {i} exhausted")


def main() -> int:
    os.makedirs(SUB_DIR, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=SUBS) as pool:
        sizes = list(pool.map(fetch, range(SUBS)))
    if sum(sizes) != WANT:
        print(f"FATAL sizes {sum(sizes)} != {WANT}")
        return 1
    tmp = OUT + ".joining"
    with open(tmp, "wb") as sink:
        for i in range(SUBS):
            with open(os.path.join(SUB_DIR, f"sub_{i:02d}"), "rb") as src:
                sink.write(src.read())
    os.replace(tmp, OUT)
    print(f"CHUNK_03_READY size={os.path.getsize(OUT)} (want {WANT})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
