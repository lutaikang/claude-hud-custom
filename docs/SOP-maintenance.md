# 维护、部署与回滚

## 修改前

先阅读 [目录索引](REFERENCE-directories.md) 和 [架构说明](ARCHITECTURE-custom-layer.md)，确定修改的是输入口径、缓存统计、显示配置还是插件本体。本仓库不包含上游完整源码；修改上游布局需要另行维护对应上游源码和构建产物。

当前三个脚本是原样收录。本次没有把实时入口改成仓库路径，也没有安装新的自动同步或更新钩子。

在仓库根目录运行：

```bash
/usr/bin/python3 -I tests/test_repository.py
/bin/bash -n src/statusline-hud-plus-cache.sh
```

需要验证上游渲染兼容性时，再显式执行真实插件集成命令，见[验证说明](TEST-validation.md)。不要求安装 npm 依赖或启动投资平台容器。

## 修改源码与来源基线

1. 在 `src/` 修改相关文件，不直接编辑安装缓存。
2. 补充合成输入及预期结果，执行受影响的定制层与真实插件测试。
3. 同步架构、配置和兼容性说明。若上游版本变化，核对完整依赖身份，不只改版本字符串。
4. `provenance.json` 的源码摘要是收录基线。源码有意变更后应保留原始来源与变更记录，再明确建立新基线；不能只重写摘要来消除测试失败。
5. 只有用户明确要求时才 stage、commit 或 push。初始化仓库不等于已有提交或远程备份。

## 部署前备份

以下是**后续明确授权部署时**的操作说明，本次仓库化没有执行这些写入。先核对实时文件与仓库差异，防止覆盖仓库化之后新增的用户修改。

备份可能含私有配置，必须保存在 `~/.claude/backups/`，不能放进仓库、日志或任务证据。下面命令在同一终端执行，失败时先处理原因，不自动继续覆盖：

```bash
set -eu
umask 077
backup="$HOME/.claude/backups/hud-custom-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$HOME/.claude/backups"
mkdir -m 700 "$backup"
for name in statusline-hud-plus-cache.sh statusline-hud.py cache-ratio-line.py settings.json; do
  if [ -f "$HOME/.claude/$name" ]; then
    cp -p "$HOME/.claude/$name" "$backup/$name"
    chmod 600 "$backup/$name"
  fi
done
printf 'Backup directory: %s\n' "$backup"
```

备份完整 settings 只是为本机恢复保全，不意味着可以把它收录仓库。若目标脚本或配置是符号链接，先确认实际目标和授权，不把上述复制流程当作链接安全安装器。

## 部署定制脚本

前提是依赖已安装、上述验证已完成、目标文件已检查和备份，且用户明确授权修改实时入口所使用的脚本。此命令从仓库根目录执行，仅复制三个文件：

```bash
for name in statusline-hud-plus-cache.sh statusline-hud.py cache-ratio-line.py; do
  cp "src/$name" "$HOME/.claude/$name"
  chmod 600 "$HOME/.claude/$name"
done
```

当前已有 `statusLine` 设置不需要重新写入。新机首次配置时，只合并 `config/statusline.example.json` 中的 `statusLine` 字段；不要拿样例覆盖整份 settings，也不要自动覆盖已有显示配置。

不要把 settings 直接指向仓库内的 Shell 脚本，然后以为仓库内全部源码已生效：该脚本依旧读取 `$HOME/.claude/statusline-hud.py`。本次保留了这个行为，而不是静默修改安装模型。

部署后逐文件比较仓库与目标摘要，在正常状态栏刷新中核对显示，并重跑适用测试。固定0.11.2测试通过不能证明实时适配器后来自动选中的新版本也兼容。

## 回滚

- 先确认备份目录确属本次部署前的快照，并查看目标文件是否又有其他修改。
- 仅恢复需要回退的三个脚本，恢复后比较摘要并实际检查状态栏。
- 如改过 `statusLine`，只恢复该字段或经检查合并配置；不要用旧全量 settings 覆盖后续其他设置。
- 显示配置未变时无需回滚显示配置。不要删除插件历史缓存、上游仓库或旧任务证据来“清理”。

## 上游更新

实时适配器按最高三段版本选择插件，更新会影响它下一次选择的目标，但不自动改变本仓库的依赖快照。更新后应核对上游版本、许可证、配置模型和输出格式，取得明确的新依赖摘要，再运行真实集成。费用替换规则、行数/颜色以及 usage 字段变化尤其需要复验。

## 排查入口

- 没有输出：先区分输入无效、缺少插件、Node 路径不存在、子进程失败/超时和渲染为空；适配器会安静处理部分错误。
- 仓库改动没生效：比较 `src/` 与 `~/.claude/`，确认维护副本已部署；不要仅看 Git diff。
- 上下文比例不符：核对代理判断、策略容量和三桶 usage；不要把原生模型别名容量当作代理后端能力。
- 缓存比例未知：检查消息是否报告未缓存输入；不要为消除“未知”补造0。
- 测试被权限门拒绝：保留原始拒绝原因，停止相关执行，不换入口或扩大权限绕过。其余验证不能改写该项状态。
