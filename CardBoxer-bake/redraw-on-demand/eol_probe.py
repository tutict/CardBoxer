from pathlib import Path

GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
for rel in ["scripts/arena.gd", "scripts/hud.gd", "scripts/fx_layer.gd"]:
    b = (GAME / rel).read_bytes()
    crlf = b.count(b"\r\n")
    print(rel, "bytes=", len(b), "CRLF=", crlf, "LF_only=", b.count(b"\n") - crlf)
