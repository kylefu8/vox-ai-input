# Codex 多电脑同步开发指南

这份文档用于在一台没有历史 session 的电脑上继续开发 Vox AI Input。

## 新电脑第一次配置

1. 安装 Git、Python 3.12、Node.js 和 Codex CLI。

```powershell
npm i -g @openai/codex@latest
codex
```

2. 克隆仓库并进入项目。

```powershell
git clone https://github.com/kylefu8/vox-ai-input.git
cd vox-ai-input
```

3. 初始化 Python 环境。

```powershell
.\scripts\bootstrap_dev.ps1
```

这个脚本的详细说明见 `docs/bootstrap-dev.md`。

4. 打开 `config.yaml`，配置本机专属内容：

- 本地 STT 模型选择
- 润色 endpoint
- API key
- 模型名称
- 悬浮按钮位置、快捷键等个人偏好

不要提交 `config.yaml`、`models/`、`data/` 或任何 API key。

## 让新 Codex 快速接上上下文

仓库根目录的 `AGENTS.md` 是 Codex 的项目级长期说明。新电脑打开仓库后，可以让 Codex 先执行：

```text
请先阅读 AGENTS.md、progress.md、findings.md、README_zh.md，然后总结当前项目状态和下一步建议。
```

如果只想确认 Codex 是否加载了项目规则，可以运行：

```powershell
codex debug prompt-input "ping" | Select-String -Pattern "AGENTS.md|Vox AI Input|Project Snapshot"
```

`.codex/config.toml.example` 是可选的个人配置模板。Codex CLI 当前主要读取 `~/.codex/config.toml`，所以不要把 API key 或个人路径写进仓库配置。

## 能不能让 Codex 自动先执行 bootstrap？

可以让 Codex “知道应该先执行”，但不建议、也不应该让仓库在 `git clone` 完成瞬间自动执行脚本。自动执行刚 clone 下来的代码有安全风险；更好的方式是把启动规则写进 `AGENTS.md`，让 Codex 在进入项目后先判断 `.venv` 和 `config.yaml` 是否存在，再运行 bootstrap。

本仓库已经在 `AGENTS.md` 的 `Fresh Clone Bootstrap` 中写入规则：

- `.venv` 不存在时，先运行 `.\scripts\bootstrap_dev.ps1 -SkipVerify`。
- 用户要求完整初始化或发布前验证时，运行 `.\scripts\bootstrap_dev.ps1`。
- `config.yaml` 不存在时，从 `config.example.yaml` 复制，但不提交。

新电脑 clone 后，你可以直接让 Codex 接管初始化：

```powershell
codex "这是一个刚 clone 的 vox-ai-input 仓库。请先按 AGENTS.md 的 Fresh Clone Bootstrap 初始化项目，然后总结结果。"
```

如果你希望用非交互命令让 Codex 执行初始化：

```powershell
codex exec "这是一个刚 clone 的 vox-ai-input 仓库。请先按 AGENTS.md 的 Fresh Clone Bootstrap 初始化项目，然后总结结果。"
```

如果 Codex 因为权限策略请求批准安装依赖或运行脚本，批准即可。不要为了省一次确认而把仓库脚本设置成 clone 后无条件自动执行。

## 两台电脑交替开发

每次开始前：

```powershell
git pull --rebase
```

每次切换电脑前：

```powershell
git status --short
git add <changed-files>
git commit -m "..."
git push
```

如果两台电脑要同时做不同方向，使用不同分支：

```powershell
git switch -c feat/polish-ui
git push -u origin feat/polish-ui
```

另一台电脑继续：

```powershell
git fetch origin
git switch feat/polish-ui
```

## 并行开发规则

- 不要让两台电脑的 Codex 同时改同一个分支上的同一批文件。
- UI、LLM client、prompt/eval、release 文档可以分成不同分支做。
- 合并前先跑：

```powershell
py -3.12 -m compileall -q run.py src tests
uv run --python 3.12 --with-requirements requirements-dev.txt python -m pytest -q
```

## 本项目的持久记忆文件

- `AGENTS.md`：给 Codex 的项目级工作规则。
- `progress.md`：开发流水和已完成事项。
- `findings.md`：重要发现、坑和产品判断。
- `task_plan.md`：阶段性计划和决策。
- `_release_note_v*.md`：每次发版的用户向说明。

新的 Codex session 没有旧聊天记录，但只要这些文件保持更新，就能比较顺滑地继续。
