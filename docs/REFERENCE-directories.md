# HUD 目录与来源索引

本索引记录 2026-10-15 仓库化整理时核对的本机路径。`~` 指用户 HOME；这些是本机位置快照，不是其他设备必须采用的目录。可移植的依赖身份在 [provenance.json](../provenance.json) 中。

## 定制源码与实时运行文件

```text
维护仓库：~/Desktop/claude-hud-custom
Git 根：  ~/Desktop/claude-hud-custom/.git

仓库源码                                本机实时文件
src/statusline-hud-plus-cache.sh    →    ~/.claude/statusline-hud-plus-cache.sh
src/statusline-hud.py               →    ~/.claude/statusline-hud.py
src/cache-ratio-line.py             →    ~/.claude/cache-ratio-line.py
```

箭头表示维护文件与部署目标的对应关系，不表示符号链接或自动同步。三个文件收录时与实时文件逐字节一致，原始摘要见来源清单。之后发生修改时，须重新比较，不能继续引用原结论。

启动设置在 `~/.claude/settings.json` 的 `statusLine` 字段；只提供 [局部配置样例](../config/statusline.example.json)，不保存用户完整设置。

## 上游源码与安装缓存

```text
上游本地 Git：~/.claude/plugins/marketplaces/claude-hud
上游 origin：  https://github.com/jarrodwatts/claude-hud.git
核对的分支：   main
核对的 HEAD：  02d73c416b52b4e510a9be004fca469f961cd5bc
核对的版本：   0.11.2

用户安装记录：~/.claude/plugins/installed_plugins.json
marketplace： ~/.claude/plugins/known_marketplaces.json
插件缓存根：  ~/.claude/plugins/cache/claude-hud/claude-hud
当前选中入口：插件缓存根/0.11.2/dist/index.js
```

上游本地 Git 当时为干净的浅克隆。其 `src/`、`dist/`、`commands/`、`tests/`、`scripts/`、`.claude-plugin/` 与 0.11.2 缓存副本逐文件一致；这不证明历史缓存与当前版本相同，也不代替运行验证。

缓存根还存在 `0.7.1`、`0.8.0`、`0.10.0`、`0.11.1`。适配器按数字选择最大 `X.Y.Z`，不读取安装记录来决定版本；marketplace 已开启自动更新。因此“今天选中0.11.2”是快照，不是永久锁定。测试单独固定0.11.2及其内容摘要。

`~/Desktop/codex-hud` 是另一仓库，其 origin 为 `https://github.com/lutaikang/codex-hud.git`，不是本仓库或 Claude HUD 上游；其项目级旧安装记录不能决定当前投资平台的状态栏入口。

## 显示配置

令 `C` 为上游插件的配置根：默认 `~/.claude`，非空 `CLAUDE_CONFIG_DIR` 可覆盖。上游读取顺序是：

```text
C/plugins/claude-hud/config.json   # 共享显示配置
  └─ C/claude-hud.json            # 可选覆盖，随后校验并补默认值
```

这里的“目录覆盖”指配置根目录，不是业务项目中的任意 `claude-hud.json`。对象递归合并，数组替换；未知键被忽略。上游在 POSIX 上拒绝配置文件本身为符号链接，但这不等于父目录不能是链接。

定制适配器对 `CLAUDE_CONFIG_DIR` 的处理与上游并非完全相同：它直接构造 `Path`，不会主动展开 `~` 或清理空白。若需要设置该变量，应使用明确的绝对路径。Shell 入口和缓存附加脚本仍使用 `$HOME/.claude/`，不会整体随该变量迁移。

仓库的 [显示样例](../config/hud-config.example.json) 只保留当前有效的显示选项。实时文件中存在的 `promptCacheTtlSeconds: 300` 不在0.11.2配置模型中，样例已排除；**实时文件未被修改**。

## 历史任务与备份

```text
历史修改说明：
~/Desktop/money/investment-platform/tasks/2026-10-13-1206-cross-context-hud-diagnostics.md

历史测试与证据：
~/Desktop/money/investment-platform/tasks/2026-10-13-1206-cross-context-hud-diagnostics/evidence/

历史文档登记的备份位置：
~/.claude/backups/hud-20261013-1206/

本次唯一任务记录：
~/Desktop/money/investment-platform/tasks/2026-10-15-1629-tooling-claude-hud-repository.md
```

历史备份位置来自旧文档，本次没有读取或验证其完整性。历史说明与证据在本次核对时未被投资平台 Git 追踪；文件存在不等于已经提交。这里仅提供位置，不复制整个证据目录、隔离 HOME 或旧日志到新仓库。
