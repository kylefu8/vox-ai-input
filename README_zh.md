# Vox AI Input

[English](README.md)

**AI 语音输入法** — 长按快捷键说话，松开后文字自动粘贴到当前应用。

> 🎤 说话 → 🤖 AI 转写 → ✨ AI 润色 → 🌐 翻译（可选）→ 📋 自动粘贴

支持中英文混合识别、口述符号自动转换（如"艾特" → @），AI 自动修正标点和语法，可选实时翻译到 9 种语言。

> **v0.0.8 悬浮麦克风 + 更强润色！** 新增可拖动录音按钮、中英文界面、深浅色切换、软件说明弹窗、可选 API 类型（含 OpenAI Responses），并升级默认语音清理 prompt。

## 功能特性

- **一键语音输入** — 长按快捷键说话，松开自动输出到当前应用
- **🆕 本地离线转写** — 集成 sherpa-onnx，无需联网，延迟极低
  - SenseVoice（推荐·中文最佳，~156MB）
  - Whisper Small（多语言通用，~610MB）
  - Paraformer 流式（中英实时转写，边说边出字）
  - 设置窗口一键下载模型
- **AI 智能润色** — 自动修正标点、去口水词、自动分段，并把口述清单整理成编号事项
- **多 API 润色端点** — 支持 OpenAI Chat Completions、OpenAI Responses、Anthropic Messages 和 OpenAI-compatible 网关
- **悬浮录音控制** — 可拖动的置顶麦克风按钮，可点击开始/停止录音，并同步快捷键/托盘状态
- **历史记录** — 自动保存最近输出，可在设置窗口回看并复制
- **中英混合识别** — 中英文夹杂也能准确识别，技术术语保留英文
- **符号口述转换** — 说"艾特"输出 @、说"井号"输出 #
- **实时翻译** — 说中文出英文（支持 9 种语言），一步到位
- **高级 Prompt 覆盖** — 默认收起，避免误改导致润色跑偏
- **录音倒计时** — 录音接近上限时屏幕右下角半透明倒数提示
- **实时日志窗口** — 深色主题滚动日志，方便排查问题
- **现代设置界面** — 左侧导航、更聚焦的页面结构，支持中文/英文界面和深色/浅色主题
- **程序图标** — Fluent 风格蓝紫渐变麦克风，应用到 exe、安装包、设置窗口
- **快捷键热更新** — 修改快捷键立即生效，无需重启
- **系统托盘常驻** — 渐变麦克风图标，状态一目了然
- **一键检查更新** — 托盘菜单一键检查 GitHub 新版本
- **配置热重载** — 所有设置修改后立即生效
- **开机自启** — 可选开机自动启动

## 环境要求

- **Windows** 10/11 (x86_64)
- **麦克风** 系统已授权访问
- **转写引擎**：设置中下载的本地离线模型
- **可选润色 API**：Azure OpenAI / OpenAI-compatible / Anthropic

## 快速开始

### 方式一：安装包（推荐）

1. 从 [Releases](https://github.com/kylefu8/vox-ai-input/releases) 下载 `VoxAIInput-Setup-x.x.x.exe`
2. 双击运行安装（支持桌面快捷方式 + 开机自启选项）
3. 首次启动会自动打开设置窗口 — 下载本地模型，并按需配置 AI 润色
4. 长按快捷键说话即可

### 方式二：免安装版

1. 下载 `VoxAIInput-x.x.x-win64.zip`
2. 解压到任意目录
3. 复制 `config.example.yaml` 为 `config.yaml`，配置你的设置
4. 双击 `VoxAIInput.exe` 运行

### 方式三：从源码运行

```powershell
# 克隆
git clone https://github.com/kylefu8/vox-ai-input.git
cd vox-ai-input

# 虚拟环境
python -m venv .venv
.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 配置
Copy-Item config.example.yaml config.yaml
# 编辑 config.yaml，填入你的设置

# 启动
python run.py
```

## 使用方法

| 操作 | 说明 |
|------|------|
| **长按快捷键** | 开始录音（托盘图标变红） |
| **松开快捷键** | 停止录音 → 转写 → 润色 → 粘贴 |
| **点击悬浮麦克风** | 开始/停止录音，状态会和快捷键同步 |
| **拖动悬浮麦克风** | 移动位置，松手后自动保存 |
| **录音中按 Esc** | 取消当前录音 |
| **托盘右键 → 设置** | 打开设置窗口 |
| **设置右上角 → 界面/主题/关于** | 切换界面语言、深浅配色，查看软件说明 |
| **托盘右键 → 日志** | 打开实时日志窗口 |
| **托盘右键 → 检查更新** | 检查 GitHub 新版本 |

### 托盘图标状态

| 图标颜色 | 状态 |
|----------|------|
| 灰蓝 | 空闲，等待输入 |
| 红色 | 录音中 |
| 金黄 | 处理中（转写 + 润色） |

### 翻译功能

在设置窗口的「常用设置」中选择翻译目标语言：

| 语言 | 代码 |
|------|------|
| 不翻译 | （默认） |
| 简体中文 / 繁体中文 | zh / zh-TW |
| 英语 / 日语 / 韩语 | en / ja / ko |
| 法语 / 德语 / 西班牙语 / 俄语 | fr / de / es / ru |

选择后说话内容会自动润色 + 翻译为目标语言，一次 API 调用完成。

### 启动参数

| 参数 | 说明 |
|------|------|
| `python run.py` | 正常模式（托盘运行） |
| `python run.py --test` | 测试模式（按回车控制录音） |
| `python run.py --visible` | 正常模式 + 保留控制台（调试用） |
| `python run.py --open-settings` | 启动应用并立即打开设置窗口 |
| `python run.py --version` | 显示版本号 |

## 配置说明

编辑 `config.yaml`（首次可从设置窗口直接配置）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `ui.language` | 设置窗口和托盘菜单语言：`zh-CN` / `en` | `zh-CN` |
| `ui.theme` | 设置窗口配色：`dark` / `light` | `dark` |
| `ui.floating_control.enabled` | 是否显示可拖动悬浮录音按钮 | `true` |
| `stt.backend` | 转写引擎，固定为本地离线 | `local` |
| `stt.model_type` | 本地模型：`sense_voice`、`whisper_small` 或 `paraformer_streaming` | `sense_voice` |
| `recording.sample_rate` | 采样率 (Hz) | `16000` |
| `recording.channels` | 声道数 | `1` |
| `recording.max_duration` | 最长录音秒数 | `60` |
| `hotkey.combination` | 录音快捷键 | `ctrl+shift+space` |
| `polish.enabled` | 是否启用 AI 润色 | `false` |
| `polish.profile` | 润色使用的 LLM profile | `default` |
| `polish.translate_to` | 翻译目标语言代码（留空不翻译） | `""` |
| `polish.show_original` | 翻译时同时输出润色后的原文 | `false` |
| `llm_profiles.default.provider` | API 类型：`auto`、`openai_compatible`、`openai_responses` 或 `anthropic` | `auto` |
| `llm_profiles.default.endpoint` | 润色 API endpoint | `""` |
| `llm_profiles.default.base_url` | 可选的运行时 API base，通常由 endpoint 自动解析填入 | 未设置 |
| `llm_profiles.default.api_key` | 润色 API Key | `""` |
| `llm_profiles.default.model` | 模型名 | `""` |
| `history.enabled` | 是否保存最近输出历史 | `true` |
| `history.max_entries` | 历史记录最多保留条数 | `100` |

### 润色 API 设置

设置窗口的“润色”页现在可以选择 API 类型，并填写 Endpoint、API Key、模型名称。`OpenAI Chat Completions` 对应 `/v1/chat/completions`，`OpenAI Responses` 对应 `/v1/responses`，`Anthropic Messages` 对应 `/v1/messages`；也可以保留自动识别。点击“获取模型”会尽量从 endpoint 拉取可用模型列表，并可在后台解析缺失的 `/v1`。界面仍显示你输入的 endpoint，实际 API base 会保存为 `base_url` 并在运行时使用。也可以手动编辑：

```yaml
polish:
  enabled: true
  profile: "default"

llm_profiles:
  default:
    provider: "openai_responses"
    endpoint: "https://api.openai.com"
    base_url: "https://api.openai.com/v1"
    api_key: "sk-..."
    model: "gpt-5.4-mini"
```

## 项目结构

```
vox-ai-input/
├── run.py                  # 程序入口
├── build.spec              # PyInstaller 打包配置（--onedir）
├── installer.iss           # Inno Setup 安装包脚本
├── config.example.yaml     # 配置模板
├── requirements.txt        # 运行依赖
├── src/
│   ├── app.py              # 主控制器，协调所有模块
│   ├── voice_pipeline.py   # 核心流程：转写 → 润色 → 输出
│   ├── runtime_components.py # 运行时组件工厂
│   ├── config.py           # 配置加载、保存与验证
│   ├── recorder.py         # 麦克风录音 + 设备检测
│   ├── audio_files.py      # 临时音频文件工具
│   ├── local_transcriber.py # 本地离线语音转文字（sherpa-onnx）
│   ├── model_manager.py    # 本地模型下载与管理
│   ├── polisher.py         # AI 文字润色 + 翻译
│   ├── llm_clients.py      # 润色 LLM provider 适配器（Azure/OpenAI-compatible/Anthropic）
│   ├── hotkey.py           # 全局热键监听
│   ├── output.py           # 剪贴板 + 模拟粘贴
│   ├── tray.py             # 系统托盘（渐变麦克风图标）
│   ├── floating_control.py # 可拖动屏幕录音按钮
│   ├── i18n.py             # 轻量中英文界面文案
│   ├── settings_window.py  # 支持深浅色主题的设置窗口
│   ├── log_window.py       # 实时日志查看窗口
│   ├── countdown.py        # 录音倒计时浮窗（Win32 Layered Window）
│   ├── updater.py          # GitHub 版本检查与更新
│   ├── notifier.py         # 提示音播放
│   ├── autostart.py        # 开机自启管理
│   ├── azure_client.py     # Azure OpenAI 客户端工厂
│   ├── paths.py            # 路径工具（兼容打包/源码模式）
│   ├── interfaces.py       # Protocol 接口定义
│   └── logger.py           # 统一日志（UTF-8 安全）
├── tests/                  # 170+ 测试用例
├── models/                 # 本地 STT 模型（用户按需下载，不含在 git 中）
├── assets/sounds/          # 录音提示音
├── scripts/                # 构建辅助脚本
└── .github/workflows/      # GitHub Actions CI/CD
```

## 开发

```powershell
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
python -m pytest tests/ -v

# 本地构建 exe
pip install pyinstaller pyinstaller-hooks-contrib
pyinstaller build.spec --clean --noconfirm
# 产物在 dist/VoxAIInput/
```

## 常见问题

**快捷键不生效**
- 确认没有其他程序占用该快捷键
- 托盘右键 → 设置 → 录制新快捷键，保存后立即生效

**粘贴时目标应用没反应**
- 部分以管理员权限运行的程序可能无法接收模拟按键
- 尝试以管理员身份运行 Vox AI Input

**翻译没生效**
- 确认设置中翻译下拉选择了目标语言并保存
- 在“润色”设置里检查提示词是否被手动改坏；必要时清空提示词恢复默认

**RDP 远程桌面无法录音**
- RDP 默认不转发麦克风，需在 RDP 客户端 → 本地资源 → 远程音频 → 设置 → 开启「从此计算机录制」

**录音太短被跳过**
- 录音不足 0.3 秒会被视为误触而跳过

## 技术栈

- **语言**: Python 3.10+
- **语音转写**: 本地 sherpa-onnx（SenseVoice / Whisper Small / Paraformer）
- **文字润色 + 翻译**: Azure OpenAI / OpenAI-compatible / Anthropic
- **热键监听**: pynput
- **录音**: sounddevice + soundfile
- **UI**: tkinter（设置窗口、日志窗口、悬浮按钮）+ pystray（系统托盘）
- **倒计时浮窗**: Win32 Layered Window（逐像素 Alpha 透明）
- **打包**: PyInstaller（--onedir）+ Inno Setup（安装包）
- **CI/CD**: GitHub Actions

## License

[MIT](LICENSE)
