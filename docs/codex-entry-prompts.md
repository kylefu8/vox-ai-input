# Codex 入口提示词

这份文档放几段可以直接复制给 Codex 的入口提示词。目标是让一台没有历史 session 的电脑，也能从 GitHub repo 自动接上当前项目状态。

## 第一次：还没有 clone 仓库

先进入你希望放项目的父目录，然后运行：

```powershell
codex "请为 GitHub repo https://github.com/kylefu8/vox-ai-input 建立本地工作区：如果当前目录下没有 vox-ai-input，就先 git clone；如果已经存在，就进入该目录。进入仓库后按 AGENTS.md 的 GitHub Sync Before Work 和 Fresh Clone Bootstrap 执行：先同步 GitHub，必要时初始化 .venv 和 config.yaml，然后阅读 AGENTS.md、progress.md、findings.md、task_plan.md、README_zh.md 和最新 release note。最后告诉我当前分支、版本、环境状态、最近完成的工作和建议的下一步。"
```

如果想用非交互模式：

```powershell
codex exec "请为 GitHub repo https://github.com/kylefu8/vox-ai-input 建立本地工作区：如果当前目录下没有 vox-ai-input，就先 git clone；如果已经存在，就进入该目录。进入仓库后按 AGENTS.md 的 GitHub Sync Before Work 和 Fresh Clone Bootstrap 执行：先同步 GitHub，必要时初始化 .venv 和 config.yaml，然后阅读 AGENTS.md、progress.md、findings.md、task_plan.md、README_zh.md 和最新 release note。最后告诉我当前分支、版本、环境状态、最近完成的工作和建议的下一步。"
```

## 已经 clone：每次开工前续上

在仓库目录运行：

```powershell
codex "这是 vox-ai-input 已初始化工作区。请先按 AGENTS.md 的 GitHub Sync Before Work 同步 GitHub：检查 git status；如果工作区干净，fetch/pull --rebase；如果有本地未提交改动，先总结并询问。同步后阅读 AGENTS.md、progress.md、findings.md、task_plan.md 和最新 release note，然后告诉我当前状态和下一步建议。"
```

## 已经 clone：让 Codex 接着做具体任务

```powershell
codex "这是 vox-ai-input 已初始化工作区。请先按 AGENTS.md 的 GitHub Sync Before Work 同步并接上项目上下文，然后继续做这个任务：<在这里写你的任务>。完成后运行相关验证，必要时更新 progress.md，并提交推送。"
```

## 需要完整初始化和测试

```powershell
codex "这是刚 clone 或刚迁移的 vox-ai-input 工作区。请按 AGENTS.md 的 Fresh Clone Bootstrap 做完整初始化，运行 .\scripts\bootstrap_dev.ps1，并报告依赖安装、config.yaml、models 目录、编译检查和 pytest 结果。"
```

## 重要边界

- 不要让 `git clone` 完成后无条件自动执行仓库脚本。
- 第一次 clone 前 Codex 还看不到仓库里的 `AGENTS.md`，所以需要用本文件里的入口提示词告诉它 repo URL 和目标流程。
- clone 之后，Codex 会在仓库内读取 `AGENTS.md`，之后就可以按项目规则持续工作。
- 如果 Codex 因权限策略要求确认 `git clone`、安装依赖或运行脚本，批准后继续即可。
