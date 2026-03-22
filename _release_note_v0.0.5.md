## Vox AI Input v0.0.5

### 🆕 本地离线语音转写

集成 [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 离线推理引擎，无需联网即可语音转文字，延迟大幅降低。

- 🖥️ **本地离线转写** — 在设置窗口新增「转写引擎」卡片，一键切换 Azure 云端 / 本地离线
- 📦 **两种离线模型可选**：
  - **SenseVoice**（推荐）— 中/英/日/韩/粤，~156MB，中文质量最佳
  - **Whisper Small** — 支持 99 种语言，~610MB
- ⬇️ **模型一键下载** — 设置窗口直接下载，进度条实时显示，下载完即可使用
- 🔌 **完全离线模式** — 本地转写 + 关闭润色 = 不需要任何 Azure 配置，零网络依赖
- 🔄 **无缝切换** — Azure / 本地随时切换，热重载无需重启，旧模型自动释放内存

### 改进

- ⚡ **config 验证逻辑优化** — 根据 STT 后端 + 润色开关动态验证 Azure 必填字段
  - 本地转写 + 润色关 → 不需要任何 Azure 配置
  - 本地转写 + 润色开 → 只需 endpoint、api_key、gpt_deployment
  - Azure 模式 → 与之前完全一致（向后兼容）
- 📝 **config.example.yaml 更新** — 新增 `stt` 配置段（backend / model_type / num_threads）
- 🧹 **.gitignore 更新** — 排除 `models/` 目录（模型文件不应提交到 git）

### 向后兼容

- 旧 config.yaml 没有 `stt` 段 → 自动使用 Azure 模式，行为完全不变
- sherpa-onnx 未安装 → 选 Azure 模式一切正常；选 Local 时给出清晰安装提示

### 下载

| 文件 | 说明 |
|------|------|
| `VoxAIInput-Setup-0.0.5.exe` | **安装包**（推荐）— 双击安装，支持桌面快捷方式 + 开机自启 |
| `VoxAIInput-0.0.5-win64.zip` | **免安装版** — 解压即用 |
| `config.example.yaml` | 配置模板 — 首次使用参考 |

### 环境要求

- Windows 10/11 (x86_64)
- 麦克风
- 转写引擎（二选一）：
  - 🖥️ 本地离线 — 无需额外配置，设置中下载模型即可
  - ☁️ Azure 云端 — [Azure AI Foundry](https://ai.azure.com/) 已部署 `gpt-4o-mini-transcribe` + `gpt-4o-mini`
