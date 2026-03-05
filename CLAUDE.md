# Vox AI Input

AI 语音输入法 — 说话即打字

## 技术栈
- Python 3.10+
- Azure AI Foundry (gpt-4o-mini-transcribe + gpt-4o-mini)
- sounddevice / soundfile / pynput / pystray / tkinter / Pillow
- PyInstaller (--onedir) + Inno Setup + GitHub Actions CI/CD

## 模型支持
- 当前版本专为 Azure AI Foundry 上 gpt-4o-mini-transcribe + gpt-4o-mini 优化
- 后续计划支持: OpenAI 直连 / 本地 Whisper / 更多模型

## 跨平台约束
- 本项目在 macOS ARM64 和 Windows x86_64 上交替开发
- 执行命令前先检测当前 OS（详见 .claude/rules/memory-preferences.md）

## 工作方式
- 实质性改动前先输出步骤计划，等我确认后再动手
- 遇到不确定的问题，优先用工具查阅或问我
- 用中文和我沟通

## 常用命令
（首次使用时请补充实际命令，删除本行提示）

## 代码风格
- 使用 4 空格缩进
- 变量/函数用 snake_case，类用 PascalCase
- 每个函数和类都要有 docstring

## Git 规范
- commit message 使用中文，格式: `<类型>: <简述>`（类型: feat/fix/refactor/docs/chore）
- 每次 commit 只做一件事

## 记忆系统
.claude/rules/ 目录下的文件会自动加载，包含环境信息、开发偏好、技术决策和会话进度。
当学到新信息时，按以下规则直接更新对应文件，无需询问：
- 用户偏好/习惯 → memory-preferences.md
- 技术选型/架构决策 → memory-decisions.md
- 任务完成/里程碑 → memory-sessions.md
