from pathlib import Path

GAME = Path(r"D:\Projects\CardBoxer\CardBoxer")
for rel, needle in (
    ("scripts/arena.gd", b"TK_MAX_TURNS"),
    ("scripts/arena.gd", b"\xe8\xbd\xae\xe6\x95\xb0\xe8\x80\x97\xe5\xb0\xbd"),  # 轮数耗尽
    ("tests/taikou_flow_check.gd", b"## 12 "),
    ("tests/taikou_flow_check.gd", b"_check_turn_limit"),
):
    data = (GAME / rel).read_bytes()
    i = data.find(needle)
    print(rel, repr(needle[:20]), "offset", i)
    if i >= 0:
        print("   ", repr(data[max(0, i - 70): i + 90]))
    print("   CRLF=%d LF_total=%d lone_LF=%d" % (
        data.count(b"\r\n"), data.count(b"\n"), data.count(b"\n") - data.count(b"\r\n"),
    ))
