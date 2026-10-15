# 来源与许可

本仓库保存已有本机定制脚本的维护副本，不代表 `claude-hud` 上游项目或其作者发布的产品。

上游依赖：

```text
repository: https://github.com/jarrodwatts/claude-hud.git
version:    0.11.2
commit:     02d73c416b52b4e510a9be004fca469f961cd5bc
license:    MIT
```

上游许可全文和版权声明保存在 [third_party/claude-hud-LICENSE](third_party/claude-hud-LICENSE)，用于说明依赖来源。此文件不等于把上游 MIT 许可自动应用到本仓库全部定制源码。

`src/` 三个文件来自用户现有本地安装，未在本次整理中修改行为。`tests/test_hud.py` 基于历史本地合成输入测试整理，调整了源码定位、依赖身份校验、临时目录清理与隔离边界；不能把它称为上游官方测试。

本次没有为定制层另外指定开源许可证，也没有发布仓库。对外分发前，应由维护者确认定制代码和新增文档的授权范围，并继续保留适用的上游版权、许可与免责声明。
