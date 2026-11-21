# 牌拳 / CardBoxer

卡牌驱动的格斗游戏，以及配套的建模、动作烘焙和实验研发资料。

## 目录

- [牌拳-CardBoxer](牌拳-CardBoxer/README.md)：可运行的 Godot 游戏主工程，包含战术卡牌、传统比牌和实时格斗模式，以及原生 3D 角色素材。
- 牌拳-CardBoxer-bake/：模型源文件、动作数据、制作脚本、实验版本、验收报告、截图和演示素材。

两部分保留原来的并列目录结构，方便研发工具按相对路径找到游戏工程。

## 获取与运行

模型、图片、动画和压缩包使用 Git LFS。克隆前安装 [Git LFS](https://git-lfs.com/)，然后运行：

```shell
git lfs install
git clone https://github.com/tutict/CardBoxer.git
```

用 Godot 4.5 或更新版本打开 `牌拳-CardBoxer/project.godot`。Windows 上也可以在游戏目录中使用 `运行游戏-3D.bat` 等启动脚本；详细操作和验证命令见游戏主工程的 README。

## 研发资料说明

研发目录保留模型、烘焙、动作接线、视觉对照和玩法实验的源文件与结果。部分工具仍保留开发时的本机绝对路径，运行前需要按环境调整。

发布时排除 Godot/Python 缓存、临时测试夹具、Blender 自动备份，以及原 `github-publish` 目录中的递归重复拷贝。
