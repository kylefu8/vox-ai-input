## Vox AI Input v0.0.7

### Local-first Refactor / 本地优先重构

This release removes online transcription from the main product path and makes local offline speech-to-text the default, primary workflow.

本版本移除主流程中的在线转写，将本地离线语音识别作为默认核心路径。

- **Local transcription only** — SenseVoice, Whisper Small, and Paraformer Streaming remain the supported transcription engines
- **No online STT setup** — Cloud APIs are now used only for optional polishing and translation
- **Cleaner runtime wiring** — Shared runtime factories keep GUI mode and test mode on the same component creation path

---

- **仅保留本地转写** — 支持 SenseVoice、Whisper Small 和 Paraformer 流式模型
- **不再需要在线转写配置** — 云端 API 只用于可选的润色和翻译
- **运行时组件收敛** — GUI 模式和测试模式复用同一套组件创建逻辑

### Polishing API Simplification / 润色 API 简化

Polishing setup is now endpoint/key/model first. Provider type is detected automatically when validating the connection.

润色配置现在只围绕 endpoint、key、model 展开；API 类型在验证连接时自动识别。

- **Multiple endpoints** — Azure OpenAI, OpenAI-compatible APIs, and Anthropic are supported
- **Automatic provider detection** — The settings window tries supported protocols and stores the working type
- **Model discovery** — The settings window can fetch model/deployment names when the endpoint exposes a model list
- **Simplified profile storage** — The default profile is saved with generic `provider`, `endpoint`, `api_key`, and `model` fields

---

- **多种端点支持** — 支持 Azure OpenAI、OpenAI-compatible API 和 Anthropic
- **自动识别 API 类型** — 设置窗口会尝试多种协议，并保存可用类型
- **模型列表获取** — endpoint 暴露模型列表时，可自动拉取模型/部署名称
- **Profile 存储简化** — 默认 profile 收敛为 `provider`、`endpoint`、`api_key`、`model`

### Settings UI Redesign / 设置界面重做

The settings window has been redesigned around a smaller set of user-facing decisions.

设置窗口围绕更少、更真实的用户决策重新设计。

- **Four focused sections** — Transcription, Polishing, Operation, and Data
- **Cleaner visual system** — Graphite/cyan desktop-tool style, clearer typography, and Windows DPI awareness
- **Fewer exposed knobs** — Threads, streaming toggles, recognition language, and prompt editing are hidden or derived automatically
- **Paraformer auto-streaming** — Selecting the Paraformer streaming model automatically enables streaming mode
- **History integrated** — History browsing, copy, clear, and retention count now live in one Data page
- **Sticky save bar** — Save/cancel actions stay visible at the bottom of the settings window

---

- **四个聚焦类目** — 转写、润色、操作、数据
- **视觉系统重做** — graphite/cyan 桌面工具风格，提升字体清晰度，并启用 Windows DPI awareness
- **减少工程参数外露** — 线程数、流式开关、识别语言和 prompt 编辑默认隐藏或自动派生
- **Paraformer 自动流式** — 选择 Paraformer 流式模型后自动启用实时转写
- **历史记录整合** — 浏览、复制、清空和保留条数合并到一个数据页
- **固定保存栏** — 保存/取消按钮始终显示在设置窗口底部

### Cleanup / 清理

- Removed the outdated `--setup` web configuration wizard
- Removed unused wake-word experiment code and hidden config fields
- Removed dead `output.paste_method` documentation/config
- Updated README and config template to match the simplified product surface

---

- 移除过时的 `--setup` Web 配置向导
- 移除未开放的唤醒词实验代码和隐藏配置字段
- 移除未生效的 `output.paste_method` 文档和配置
- 更新 README 和配置模板，使其与当前简化后的产品形态一致

### Verification / 验证

- `py -3.12 -m compileall -q run.py src tests`
- `pytest -q` — 143 tests passed

### Download / 下载

| File | Description |
|------|-------------|
| `VoxAIInput-Setup-0.0.7.exe` | **Installer** (recommended) — Double-click to install |
| `VoxAIInput-0.0.7-win64.zip` | **Portable** — Extract and run |
| `config.example.yaml` | Config template |

