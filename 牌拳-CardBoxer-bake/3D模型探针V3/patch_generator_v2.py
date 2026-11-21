"""LOCAL compatibility patch #2 for the V2 probe's generator copy.

V1 widened the bundled client-side prefix check from `ck_t_` to also accept
`tk_`. In this session the desktop credential is a `ck_` Client API Key (the
segment after `ck_` varies between calls), and the server rejects `tk_` with
"invalid temp key" (see probe_run.log, first run). Accept the whole `ck_`
family rather than hard-coding one observed segment.

This patch ONLY widens a local *format* check in the copy that lives beside
this probe. Signing and server-side authentication are untouched; no credential
is stored, forged, or upgraded here. The installed WorkBuddy script is unchanged.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "generator_local.py"
src = TARGET.read_text(encoding="utf-8")

old = 'if not token.startswith(("ck_t_", "tk_")):'
new = 'if not token.startswith(("ck_", "tk_")):'
assert src.count(old) == 1, f"expected one prefix check, got {src.count(old)}"

msg_old = '"message": "Only a short-lived ck_t_ Client API Key is accepted.",'
msg_new = '"message": "Only a short-lived Client API Key is accepted.",'
assert src.count(msg_old) == 1, f"expected one message, got {src.count(msg_old)}"

note = (
    "# LOCAL ADAPTER #2 - client-side credential FORMAT check only.\n"
    "# This session issues ck_ Client API Keys; tk_ is rejected server-side.\n"
    "# Signing / server-side authentication unchanged. No credential stored here.\n"
)
out = note + src.replace(old, new).replace(msg_old, msg_new)
TARGET.write_text(out, encoding="utf-8")
print(f"PATCH_V2_OK bytes={len(out)} prefixes=ck_|tk_")
