# HUD 定制层架构与指标口径

定制层位于 Claude Code 与上游 HUD 之间：先修正需要明确口径的输入，再让上游渲染，最后附加输入 token 复用统计。它不调用模型 API、不决定代理路由，也不验证本次请求实际由哪个上游模型处理。

## 调用与文件职责

```text
Claude Code 的 statusLine JSON
  └─ statusline-hud-plus-cache.sh
       └─ /usr/bin/python3 -I $HOME/.claude/statusline-hud.py
            ├─ 读取并适配 JSON
            ├─ /opt/homebrew/bin/node C/plugins/cache/claude-hud/claude-hud/<版本>/dist/index.js
            │    └─ 上游加载显示配置、收集所需信息并渲染
            └─ /usr/bin/python3 -I $HOME/.claude/cache-ratio-line.py
                 └─ 读取 transcript_path，输出缓存统计附加行
```

这里 `C` 默认是 `$HOME/.claude`；覆盖变量的处理差异见[目录索引](REFERENCE-directories.md)。仓库源码对应上述同名文件，但不会自动成为实时入口。

## 代理场景的数据适配

`src/statusline-hud.py` 将有 hostname、且 hostname 不在 `api.anthropic.com`、`api.us.anthropic.com` 中的 `ANTHROPIC_BASE_URL` 视为自定义代理。未设 URL 或无法取得 hostname 时，不进入该分支；这是一条本地判断规则，不是服务商身份认证。

代理分支的主要处理如下：

- 模型字段优先使用 `model.id`，显示为“请求 …”；可识别的家族另读取对应 `ANTHROPIC_DEFAULT_<FAMILY>_MODEL_NAME`，标为“配置名 …”。两者都不能证明实际服务模型。
- 若 `CLAUDE_CODE_MAX_CONTEXT_TOKENS` 可转换为范围1000至10000000的数值，且存在 `context_window` 对象，则替换其容量。该值是选定策略容量，不是测得的服务商硬能力。
- `current_usage.input_tokens` 必须是非负整数，其他两个 token 桶若出现也必须有效；三桶相加除以策略容量，比例上限100%。否则清除实时 usage 和旧比例，并在模型字段标注 `usage待报告`。
- 移除 `rate_limits` 和 `prompt_cache`，避免把原生指标误当作代理后端的额度或缓存有效期。
- 对插件输出中匹配 `Cost`、`Today`、`Week`、`费用`、`成本`、`今日`、`本周` 加美元金额的文本，替换为“实付未知”。这是特定文本规则，不是通用账单验证器；上游输出变化需要重新测试。

本仓库的合成输入设定容量1M、原比例25%、三桶为20k/30k/200k。在500k策略下应传给插件50%的比例；未设置代理分支时保留原字段。这是构造案例，不是本次真实会话用量或服务商能力证明。

## 插件发现与故障边界

适配器只接受目录名完全匹配 `X.Y.Z` 且存在 `dist/index.js` 的候选，按数字三元组选择最大值。带预发布后缀或 commit 名称的目录不会入选。当前运行是动态选择，测试依赖则固定版本并校验内容，两者不能混同。

Node 子进程和缓存行子进程各有3秒超时。Node 启动失败、超时或没有成功输出时，仍会尝试缓存附加行。输入不是 JSON 对象或超过262144个文本字符（Python `str` 长度）时直接安静退出；这里不是UTF-8字节数限制。部分错误被吞掉以免污染状态栏，因此“没有报错”不等于插件成功渲染。

## 缓存复用统计

`src/cache-ratio-line.py` 只读取输入指定的 `transcript_path`。它保留 `type=assistant` 且含有效 usage 的消息，以 `message.id` 或记录 `uuid` 为标识，对每个 token 字段取有效最大值，再跨消息求和。这样不会把相同消息的多条 usage 记录逐条累加；它也不等于采用最后一条记录的完整快照。

```text
输入 token 复用率 = cache_read_input_tokens /
  (input_tokens + cache_creation_input_tokens + cache_read_input_tokens)
```

缺少未缓存输入字段时显示未知，不编造100%。只统计记录实际报告的字段；这不是 HTTP 请求命中率、缓存读写比、模型回答复用率或费用节省金额。三桶相加的前提是输入字段采用互不包含的口径；换用其他转换器时须重新核对，不能直接套用到 inclusive input 计数。

统计缓存写入系统临时目录，文件名包含用户 UID 和对话路径摘要。命中条件包含设备、inode、大小和纳秒修改时间。读取时拒绝跟随缓存文件符号链接，要求当前用户所有且不向组/其他用户开放；重算后用临时文件原子替换。它不是共享数据库，也不保存真实对话正文。

## 兼容性范围

归档脚本只导入 Python 标准库；本机核对的系统 Python 为3.9.6，Node 为v26.8.2，上游声明 Node >=18。已知绝对可执行路径是当前安装的限制，本次没有顺便改成跨平台实现。上游 MIT 来源、版本和摘要见来源清单；真实0.11.2集成验收状态见[验证说明](TEST-validation.md)。
