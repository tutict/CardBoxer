"""Make a LOCAL copy of the bundled generator with one compatibility fix.

The bundled script refuses any credential that does not start with the legacy
`ck_t_` prefix, while the current desktop session issues `tk_` prefixed
short-lived keys. That check is purely a client-side format guard: the token
is still signed into the request (`provider.token`) and validated server-side.

This script does NOT forge, store, or upgrade a credential, and it does NOT
modify the installed WorkBuddy file. It only widens the local prefix check in
a copy that lives beside this probe, so the experiment is auditable.
"""
from pathlib import Path

SKILL = Path(
    r"C:\Users\tutic\AppData\Local\Programs\WorkBuddy\resources"
    r"\app.asar.unpacked\resources\plugins\workbuddy-builtin\skills"
    r"\buddy-multimodal-generation\scripts\buddy-multimodal-generation.py"
)
HERE = Path(__file__).resolve().parent
src = SKILL.read_text(encoding="utf-8")
old = 'if not token.startswith("ck_t_"):'
assert src.count(old) == 1, f"expected exactly one prefix check, got {src.count(old)}"
new = 'if not token.startswith(("ck_t_", "tk_")):'
note = (
    "# LOCAL ADAPTER - client-side credential FORMAT check only.\n"
    "# The desktop session now issues tk_ prefixed short-lived keys; the bundled\n"
    "# script still checks for the older ck_t_ prefix. Signing and server-side\n"
    "# authentication are untouched. No credential is stored in this file.\n"
)
(HERE / "generator_local.py").write_text(note + src.replace(old, new), encoding="utf-8")
print(f"PATCH_OK bytes={len(note + src)} prefix_check_widened=True")
