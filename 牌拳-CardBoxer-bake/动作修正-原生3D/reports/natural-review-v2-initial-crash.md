# Owned initial probe crash — 2026-11-20

This records the original tool output; it is not a new engine run.

- Exec session: `50024`, launched at approximately `12:38:31` local time.
- Command: `C:/Users/tutic/Documents/godot/Godot_v4.5-stable_win64_console.exe --headless --path C:/Users/tutic/Desktop/学习资料/牌拳-CardBoxer-bake/动作修正-原生3D/project --script C:/Users/tutic/Desktop/学习资料/牌拳-CardBoxer-bake/动作修正-原生3D/reports/natural-review-v2-probe.gd`.
- Mistake: that command omitted an explicit writable `--log-file`.
- Original first error: `ERROR: Failed to open 'user://logs/godot2026-11-20T12.38.31.log'.` at `copy (core/io/dir_access.cpp:423)`.
- The engine then reported `CrashHandlerException: Program crashed with signal 11`, version `Godot Engine v4.5.stable.official (876b290332ec6f2e6d173d08162a02aa7e6ca46d)`.
- Backtrace contained 15 frames, each `error(-1): no debug info in PE/COFF executable`, followed by `-- END OF C++ BACKTRACE --`.
- I sent Ctrl+C through `write_stdin(session_id=50024)`. The owned command session returned exit code 1. The tool did not return a child PID.
- A subsequent correctly configured probe used the actual writable `reports/natural-review-v2-probe-engine.log`, exited 0 and produced the recorded numerical result. Its saved stdout/engine logs therefore describe the later successful run, not this first launch's failure.

When asked to investigate the later popup, no further validation was launched. Sandbox CIM command-line inventory failed with `无法从客户端中访问 CIM 资源`. Two scoped escalated read attempts were not executed because automatic review failed to decrypt/decode its response after the stream disconnected. I did not guess a PID or terminate a process.

Two subsequent ordinary read-only `Get-Process` inventories returned no accessible Godot or WerFault process. No main-game process was touched. The original command session is closed; no matching owned process was visible in those inventories. Every future Godot command must include an explicit real writable `--log-file`; never default logging or NUL.
