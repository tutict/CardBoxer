# 自然动作 V2 交付说明

自然动作 V2 已安装到主游戏：
`D:/Projects/CardBoxer/CardBoxer`。

双方各 19 种动作已更新，覆盖 12 张牌、3 种反应、待机、步行和倒地。
护架更紧凑，刺拳减少大幅后拉，交叉攻击由转髋带动；扫腿保持低位弧线，
上勾拳先下沉再上升，收手先于身体完全回正，进退步与动作衔接更连续。
命中定格和原有玩法时序保留。

主游戏启动入口：

- [回合制](D:/Projects/CardBoxer/CardBoxer/play.bat)
- [实时格斗](D:/Projects/CardBoxer/CardBoxer/play-realtime.bat)

预览与核验：

- [正常速度，6.92 秒](D:/Projects/CardBoxer/CardBoxer-bake/native-3d-motion-fix/reports/natural-preview-v2.gif)
- [三倍慢放，20.75 秒](D:/Projects/CardBoxer/CardBoxer-bake/native-3d-motion-fix/reports/natural-preview-v2-slow.gif)
- [正常出生位置的对局动作](D:/Projects/CardBoxer/CardBoxer-bake/native-3d-motion-fix/reports/natural-v2-normal-match-review/normal-spawn-flow.gif)

候选工程 18 组回归全部通过；主工程安装后 11 项检查通过，两种模式开启
3D 的实际集成检查分别为 14/14。32 个候选文件与主工程逐文件哈希一致。
3,004 张全动作截图和 830 张连续时间轴截图无空图或裁切。新的 V2 正常
开局完整对局在第 2,629 帧完成结算，121 张截图的逻辑位置保持 430/850。

启动器已改用 `%TEMP%/CardBoxerLogs` 中的独立可写日志。本次正常对局和
安装后检查均正常退出，未再出现访问冲突。此前 `NUL` 或默认日志写入失败
引起的引擎崩溃记录保留在核验报告中。

沿用原模型、骨架和服装。现有手模型仍为张开手型，前臂朝向改善了护架和
出招轮廓；脚步是克制的小步调整，布料沿用原有蒙皮，没有新增布料物理。

本次更新的回退备份在
`native-3d-motion-fix/updates/natural-v2/before/`，逐文件回执为同级
`update-receipt.json`；最初安装前备份仍保存在 `installed-backup/`。
当前主工程回执是 `reports/install-receipt.json`，`last_update=natural-v2`。
原安装器不可再次用于覆盖已有版本。
