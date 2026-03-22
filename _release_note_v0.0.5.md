## Vox AI Input v0.0.5

### 🆕 Local Offline Transcription / 本地离线语音转写

Integrated [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) offline inference engine for speech-to-text without internet, with significantly reduced latency.

集成 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 离线推理引擎，无需联网即可语音转文字，延迟大幅降低。

- 🖥️ **Local offline transcription** — New "Transcription Engine" card in settings, one-click switch between Azure cloud / local offline
- 📦 **Two offline models available**:
  - **SenseVoice** (recommended) — Chinese/English/Japanese/Korean/Cantonese, ~156MB, best Chinese quality
  - **Whisper Small** — 99 languages, ~610MB
- ⬇️ **One-click model download** — Download directly from settings, real-time progress bar
- 🔌 **Fully offline mode** — Local transcription + polishing disabled = zero Azure config needed, zero network dependency
- 🔄 **Seamless switching** — Switch between Azure / local anytime, hot-reload without restart, old model auto-released from memory

---

- 🖥️ **本地离线转写** — 设置窗口新增「转写引擎」卡片，一键切换 Azure 云端 / 本地离线
- 📦 **两种离线模型可选**：
  - **SenseVoice**（推荐）— 中/英/日/韩/粤，~156MB，中文质量最佳
  - **Whisper Small** — 支持 99 种语言，~610MB
- ⬇️ **模型一键下载** — 设置窗口直接下载，进度条实时显示，下载完即可使用
- 🔌 **完全离线模式** — 本地转写 + 关闭润色 = 不需要任何 Azure 配置，零网络依赖
- 🔄 **无缝切换** — Azure / 本地随时切换，热重载无需重启，旧模型自动释放内存

### Improvements / 改进

- ⚡ **Config validation optimization** — Azure required fields dynamically validated based on STT backend + polishing toggle
- 📝 **config.example.yaml updated** — New `stt` section (backend / model_type / num_threads)
- 🧹 **.gitignore updated** — Excludes `models/` directory

---

- ⚡ **config 验证逻辑优化** — 根据 STT 后端 + 润色开关动态验证 Azure 必填字段
- 📝 **config.example.yaml 更新** — 新增 `stt` 配置段（backend / model_type / num_threads）
- 🧹 **.gitignore 更新** — 排除 `models/` 目录

### Backward Compatibility / 向后兼容

- Old config.yaml without `stt` section → defaults to Azure mode, behavior unchanged
- sherpa-onnx not installed → Azure mode works fine; selecting Local shows a clear install prompt

---

- 旧 config.yaml 没有 `stt` 段 → 自动使用 Azure 模式，行为完全不变
- sherpa-onnx 未安装 → 选 Azure 模式一切正常；选 Local 时给出清晰安装提示

### Download / 下载

| File | Description |
|------|-------------|
| `VoxAIInput-Setup-0.0.5.exe` | **Installer** (recommended) — Double-click to install, supports desktop shortcut + auto-start |
| `VoxAIInput-0.0.5-win64.zip` | **Portable** — Extract and run |
| `config.example.yaml` | Config template |

### Requirements / 环境要求

- Windows 10/11 (x86_64)
- Microphone / 麦克风
- Transcription engine (choose one / 二选一):
  - 🖥️ Local offline — No extra setup, download model in settings / 本地离线 — 无需额外配置，设置中下载模型即可
  - ☁️ Azure cloud — [Azure AI Foundry](https://ai.azure.com/) with `gpt-4o-mini-transcribe` + `gpt-4o-mini`
