# Vox AI Input

**AI 语音输入法** — 长按快捷键说话，松开后文字自动粘贴到当前应用。

> 🎤 说话 → 🤖 AI 转写 → ✨ AI 润色 → 🌐 翻译（可选）→ 📋 自动粘贴

支持中英文混合识别、口述符号自动转换（如"艾特" → @），AI 自动修正标点和语法，可选实时翻译到 9 种语言。
> **当前版本专为 [Azure AI Foundry](https://ai.azure.com/) 上部署的 `gpt-4o-mini-transcribe`（语音转写）和 `gpt-4o-mini`（文字润色）模型优化。后续版本将支持更多模型和提供商（OpenAI 直连、本地 Whisper 等）。**
## 功能特性

- **一键语音输入** — 长按快捷键说话，松开自动输出到当前应用
- **AI 智能润色** — 自动修正标点、语法、去口语填充词
- **中英混合识别** — 中英文夹杂也能准确识别，技术术语保留英文
- **符号口述转换** — 说"艾特"输出 @、说"井号"输出 #
- **实时翻译** — 说中文出英文（支持 9 种语言），一步到位
- **自定义 Prompt** — 高级设置中可自由编辑润色提示词
- **录音倒计时** — 录音接近上限时屏幕右下角半透明倒数提示
- **实时日志窗口** — 深色主题滚动日志，方便排查问题
- **现代设置界面** — 深色主题卡片式布局，所有配置可视化编辑
- **快捷键热更新** — 修改快捷键立即生效，无需重启
- **系统托盘常驻** — 渐变麦克风图标，状态一目了然
- **一键检查更新** — 托盘菜单一键检查 GitHub 新版本
- **配置热重载** — 所有设置修改后立即生效
- **开机自启** — 可选开机自动启动

## 环境要求

- **Windows** 10/11 (x86_64)
- **[Azure AI Foundry](https://ai.azure.com/)** 已部署以下模型：
  - `gpt-4o-mini-transcribe` — 语音转写
  - `gpt-4o-mini` — 文字润色 + 翻译
- **麦克风** 系统已授权访问

## 快速开始

### 方式一：安装包（推荐）

1. 从 [Releases](https://github.com/kylefu8/vox-ai-input/releases) 下载 `VoxAIInput-Setup-x.x.x.exe`
2. 双击运行安装（支持桌面快捷方式 + 开机自启选项）
3. 首次启动会自动创建 `config.yaml`，打开设置窗口填入 Azure API 信息
4. 长按快捷键说话即可

### 方式二：免安装版

1. 下载 `VoxAIInput-x.x.x-win64.zip`
2. 解压到任意目录
3. 复制 `config.example.yaml` 为 `config.yaml`，填入 Azure 端点和 API Key
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
# 编辑 config.yaml，填入 Azure 端点和 API Key

# 启动
python run.py
```

## 使用方法

| 操作 | 说明 |
|------|------|
| **长按快捷键** | 开始录音（托盘图标变红） |
| **松开快捷键** | 停止录音 → 转写 → 润色 → 粘贴 |
| **录音中按 Esc** | 取消当前录音 |
| **托盘右键 → 设置** | 打开设置窗口 |
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
| `python run.py --version` | 显示版本号 |

## 配置说明

编辑 `config.yaml`（首次可从设置窗口直接配置）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `azure.endpoint` | Azure OpenAI 端点 URL | *必填* |
| `azure.api_key` | Azure OpenAI API Key | *必填* |
| `azure.api_version` | API 版本 | `2025-01-01-preview` |
| `azure.whisper_deployment` | 语音转写模型部署名 | `whisper` |
| `azure.gpt_deployment` | GPT 润色模型部署名 | `gpt-4o-mini` |
| `recording.sample_rate` | 采样率 (Hz) | `16000` |
| `recording.channels` | 声道数 | `1` |
| `recording.max_duration` | 最长录音秒数 | `60` |
| `hotkey.combination` | 录音快捷键 | `alt+z` |
| `polish.enabled` | 是否启用 AI 润色 | `true` |
| `polish.language` | 语音识别语言（留空自动检测） | `""` |
| `polish.translate_to` | 翻译目标语言代码（留空不翻译） | `""` |
| `polish.system_prompt` | 自定义润色提示词（留空用默认） | `""` |

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
│   ├── config.py           # 配置加载、保存与验证
│   ├── recorder.py         # 麦克风录音 + 设备检测
│   ├── transcriber.py      # Azure 语音转文字
│   ├── polisher.py         # AI 文字润色 + 翻译
│   ├── hotkey.py           # 全局热键监听
│   ├── output.py           # 剪贴板 + 模拟粘贴
│   ├── tray.py             # 系统托盘（渐变麦克风图标）
│   ├── settings_window.py  # 深色主题设置窗口
│   ├── log_window.py       # 实时日志查看窗口
│   ├── countdown.py        # 录音倒计时浮窗（Win32 Layered Window）
│   ├── updater.py          # GitHub 版本检查与更新
│   ├── notifier.py         # 提示音播放
│   ├── autostart.py        # 开机自启管理
│   ├── azure_client.py     # Azure OpenAI 客户端工厂
│   ├── paths.py            # 路径工具（兼容打包/源码模式）
│   ├── interfaces.py       # Protocol 接口定义
│   └── logger.py           # 统一日志（UTF-8 安全）
├── tests/                  # 120+ 测试用例
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
- 展开高级设置检查 prompt 末尾是否有翻译指令

**RDP 远程桌面无法录音**
- RDP 默认不转发麦克风，需在 RDP 客户端 → 本地资源 → 远程音频 → 设置 → 开启「从此计算机录制」

**录音太短被跳过**
- 录音不足 0.3 秒会被视为误触而跳过

## 技术栈

- **语言**: Python 3.10+
- **语音转写**: Azure AI Foundry (gpt-4o-mini-transcribe)
- **文字润色 + 翻译**: Azure AI Foundry (gpt-4o-mini)
- **热键监听**: pynput
- **录音**: sounddevice + soundfile
- **UI**: tkinter（深色主题设置窗口 + 日志窗口）+ pystray（系统托盘）
- **倒计时浮窗**: Win32 Layered Window（逐像素 Alpha 透明）
- **打包**: PyInstaller（--onedir）+ Inno Setup（安装包）
- **CI/CD**: GitHub Actions

## License

[MIT](LICENSE)
