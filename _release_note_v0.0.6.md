## Vox AI Input v0.0.6

### 🆕 Streaming Real-time Transcription / 流式实时转写

New Paraformer streaming model — words appear on screen as you speak, no more waiting until you stop recording.

新增 Paraformer 流式模型——边说边出字，不再需要录完才开始转写。

- 🎤 **Real-time streaming transcription** — Text appears live while you speak using sherpa-onnx OnlineRecognizer
- 📦 **Paraformer Streaming model** — Chinese-English bilingual, download in settings (~237MB INT8)
- 🔄 **Seamless mode switching** — Streaming / non-streaming toggle in settings, all existing models unaffected

---

- 🎤 **实时流式转写** — 使用 sherpa-onnx OnlineRecognizer，录音同时文字实时显示
- 📦 **Paraformer 流式模型** — 中英双语，设置窗口一键下载（~237MB INT8）
- 🔄 **模式无缝切换** — 设置中开关流式/非流式，现有模型完全不受影响

### 🧠 Polishing Model Upgrade / 润色模型升级

Switched polishing model from gpt-4o-mini to gpt-5.4-nano — fixing critical issues where the old model would answer questions, refuse requests, or calculate results instead of just polishing text.

润色模型从 gpt-4o-mini 切换到 gpt-5.4-nano——修复了旧模型回答问题、拒绝请求、计算结果等严重问题，现在只做文字修正。

- ⚡ **gpt-5.4-nano** — Faster, cheaper, natively follows instructions without hacks
- 🚫 **No more answering questions** — Input "What's the weather today?" now correctly outputs "What's the weather today?" instead of making up an answer
- 🏷️ **XML tag wrapping** — User input wrapped in `<speech_transcript>` tags to clearly separate data from dialogue
- 🔧 **Prompt rewrite** — Role-locked as "text correction tool, not a conversational AI", with strict prohibition rules

---

- ⚡ **gpt-5.4-nano** — 更快更便宜，原生遵守指令无需额外 hack
- 🚫 **不再回答问题** — 输入"今天天气怎么样"正确输出"今天天气怎么样？"而不是编造天气回答
- 🏷️ **XML 标签包裹** — 用户输入用 `<speech_transcript>` 标签包裹，明确区分数据和对话
- 🔧 **Prompt 重写** — 角色锁定为「纯文本修正工具，非对话AI」，严格禁止回答/回应/解读

### 🐛 Bug Fixes / 缺陷修复

- 🌐 **Translation fix** — Non-English target languages (Japanese, Traditional Chinese, etc.) now translate correctly
- 🌐 **Original language preserved** — In "translate + show original" mode, English input stays English (was incorrectly converted to Chinese)
- 🌐 **"Only translate" mode fix** — Removed incorrect rule "don't translate if already target language" that caused translation failures
- ⚙️ **Settings prompt persistence fix** — Default prompt no longer gets "baked" into config.yaml, code updates now take effect immediately
- 🔧 **Config reload order fix** — Language setting now updates before transcriber creation
- 🛡️ **Transcriber readiness check** — Recording blocked when transcriber is not initialized
- 🧹 **Temp file cleanup** — Audio files properly cleaned up in concurrent early-exit paths
- ⚙️ **Streaming field residual fix** — Switching to Azure backend now explicitly resets streaming flag

---

- 🌐 **翻译修复** — 非英文目标语言（日语、繁体中文等）现在能正确翻译
- 🌐 **原文语言保持** — 「翻译+显示原文」模式下，英文输入保持英文原文（之前会被转成中文）
- 🌐 **「仅翻译」模式修复** — 去掉了「原文已是目标语言则不翻译」的误判规则
- ⚙️ **设置提示词持久化修复** — 默认 prompt 不再被固化到 config.yaml，代码更新后立即生效
- 🔧 **配置重载顺序修复** — 语言设置现在在创建转写器之前更新
- 🛡️ **转写器就绪检查** — 转写器未初始化时阻止录音
- 🧹 **临时文件清理** — 并发早退路径中正确清理音频文件
- ⚙️ **流式字段残留修复** — 切换到 Azure 后端时显式重置 streaming 标志

### Download / 下载

| File | Description |
|------|-------------|
| `VoxAIInput-Setup-0.0.6.exe` | **Installer** (recommended) — Double-click to install |
| `VoxAIInput-0.0.6-win64.zip` | **Portable** — Extract and run |
| `config.example.yaml` | Config template |

### Requirements / 环境要求

- Windows 10/11 (x86_64)
- Microphone / 麦克风
- Transcription engine (choose one / 二选一):
  - 🖥️ Local offline — No extra setup, download model in settings / 本地离线 — 无需额外配置，设置中下载模型即可
  - ☁️ Azure cloud — [Azure AI Foundry](https://ai.azure.com/) with `gpt-4o-mini-transcribe` + `gpt-5.4-nano`
