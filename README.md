# Claude HUD 定制层

管理本机已有的 Claude HUD 适配脚本、合成输入测试和维护文档。**本仓库不是 `claude-hud` 的完整 fork，也不会自动替换当前状态栏。**

三个运行脚本从现有安装逐字节收录，来源和 SHA256 见 [provenance.json](provenance.json)。未复制全量 Claude Code 设置、凭据、真实对话、插件缓存或 `node_modules`。

## 目录

```text
claude-hud-custom/
├── src/
│   ├── statusline-hud-plus-cache.sh   # 现有启动入口
│   ├── statusline-hud.py              # 输入适配、插件选择和输出修正
│   └── cache-ratio-line.py            # 对话记录中的输入 token 复用统计
├── config/
│   ├── hud-config.example.json        # 安全显示配置样例
│   ├── statusline.example.json        # settings.json 的局部片段
│   └── input.example.json            # 合成状态栏输入，无真实对话
├── tests/
│   ├── test_repository.py            # 来源、文档及受控定制层回归
│   └── test_hud.py                   # 固定上游版本的真实插件集成
├── docs/                             # 架构、目录、维护与验证说明
├── third_party/claude-hud-LICENSE     # 上游 MIT 许可全文
├── provenance.json                   # 收录与上游依赖快照
├── NOTICE.md
└── CLAUDE.md
```

## 从哪里开始

- 找源码与当前运行目录：[目录索引](docs/REFERENCE-directories.md)。
- 理解数据处理和指标含义：[定制层架构](docs/ARCHITECTURE-custom-layer.md)。
- 修改、备份、部署和回滚：[维护说明](docs/SOP-maintenance.md)。
- 查测试命令、结果和未覆盖范围：[验证说明](docs/TEST-validation.md)。

## 本地检查

定制脚本仅使用 Python 标准库。现有启动方式针对 macOS，明确调用 `/usr/bin/python3` 和 `/opt/homebrew/bin/node`；不能据此宣称支持任意操作系统或 Node 安装位置。

先切换到本仓库目录，执行不加载上游插件的检查：

```bash
/usr/bin/python3 -I tests/test_repository.py
/bin/bash -n src/statusline-hud-plus-cache.sh
```

真实插件集成另外需要 macOS `sandbox-exec`、上述 Homebrew Node，以及与 `provenance.json` 完全匹配的上游 0.11.2：

```bash
/usr/bin/python3 -I tests/test_hud.py \
  --plugin-root "$HOME/.claude/plugins/cache/claude-hud/claude-hud/0.11.2"
```

它在临时 HOME 中运行归档脚本，只使用合成数据，阻止网络与真实 HOME 内容读取，并限制写入测试目录。**本次整理时该命令被执行权限门拦截，尚未取得运行结果**；不能把其他检查通过当作它已通过。

## 与现有安装的关系

当前安装仍通过以下文件启动：

```text
~/.claude/settings.json
  └─ ~/.claude/statusline-hud-plus-cache.sh
       └─ ~/.claude/statusline-hud.py
            ├─ 插件缓存/<最高三段版本>/dist/index.js
            └─ ~/.claude/cache-ratio-line.py
```

本仓库中的 `src/` 是维护副本，不是上述实时目录。修改它后，必须先验证，再按维护说明显式部署，才会影响状态栏。不要直接运行仓库内的 Shell 入口来验证仓库源码：该入口仍按原行为转发到 `$HOME/.claude/`，可能运行的不是你刚修改的文件。

## Git 与许可

已初始化本地 Git，初始分支为 `main`；没有自动暂存、提交、添加远程或推送。未经明确授权，不执行这些动作。上游使用 MIT；定制层尚未单独指定公开发布许可，见 [NOTICE.md](NOTICE.md)。
