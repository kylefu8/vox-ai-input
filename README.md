# VoxAI

**AI 驱动的语音输入法** — 长按快捷键说话，松开后文字自动粘贴到当前应用。

> 🎤 说话 → 🤖 AI 转写 → ✨ AI 润色 → 📋 自动粘贴

支持中英文混合识别、口述符号自动转换（如"艾特" → @），AI 自动修正标点和语法。

## 功能特性

- **一键语音输入**：长按 `Alt+Z` 说话，松开自动输出
- **AI 智能润色**：自动修正标点、语法、格式
- **中英混合识别**：中英文夹杂也能准确识别
- **符号口述转换**：说"艾特"输出 @、说"井号"输出 #
- **系统托盘常驻**：状态实时可见（空闲/录音/处理中）
- **可视化设置**：托盘右键 → 设置，修改 API、快捷键等
- **快捷键录制**：设置窗口中按键捕捉，自动检测冲突
- **配置热重载**：修改配置无需重启即刻生效
- **开机自启**：可选开机自动启动

## 环境要求

- **Windows** 10/11 (x86_64)
- **Python** 3.10+
- **Azure OpenAI** 需要已部署语音转写模型（如 gpt-4o-mini-transcribe）和 GPT 模型
- **麦克风** 系统已授权访问

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/your-username/VoxAI.git
cd VoxAI
```

### 2. 创建虚拟环境

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. 安装依赖

```powershell
pip install -r requirements.txt
```

### 4. 配置 Azure API

```powershell
Copy-Item config.example.yaml config.yaml
```

编辑 `config.yaml`，填入你的 Azure 端点和 API Key。

### 5. 启动

```powershell
python run.py
```

启动后长按 `Alt+Z` 说话，松开后文字自动粘贴到当前光标位置。

## 使用方法

| 操作 | 说明 |
|------|------|
| 长按 `Alt+Z` | 开始录音（系统托盘变红） |
| 松开 `Alt+Z` | 停止录音 → AI 转写 → 润色 → 粘贴 |
| 录音中按 `Esc` | 取消当前录音 |
| 托盘右键 → 设置 | 打开设置窗口 |
| 托盘右键 → 退出 | 关闭程序 |

### 系统托盘状态

| 颜色 | 状态 |
|------|------|
| ⚪ 灰色 | 空闲，等待输入 |
| 🔴 红色 | 录音中 |
| 🟡 黄色 | 处理中（转写 + 润色） |

### 测试模式

```powershell
python run.py --test
```

用回车键控制录音，方便在终端中调试。

### 调试日志

```powershell
$env:AI_INPUT_LOG_LEVEL="DEBUG"; python run.py
```

## 配置说明

编辑 `config.yaml`（从 `config.example.yaml` 复制）：

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

## 项目结构

```
VoxAI/
├── run.py                  # 程序入口
├── config.example.yaml     # 配置模板
├── requirements.txt        # 运行依赖
├── requirements-dev.txt    # 开发依赖（含 pytest）
├── src/
│   ├── app.py              # 主控制器，协调所有模块
│   ├── config.py           # 配置加载、保存与验证
│   ├── hotkey.py           # 全局热键监听
│   ├── recorder.py         # 麦克风录音
│   ├── transcriber.py      # 语音转文字（Azure OpenAI）
│   ├── polisher.py         # AI 文字润色（Azure GPT）
│   ├── output.py           # 剪贴板粘贴
│   ├── notifier.py         # 提示音播放
│   ├── tray.py             # 系统托盘图标
│   ├── settings_window.py  # 设置窗口（tkinter）
│   ├── autostart.py        # 开机自启管理
│   ├── azure_client.py     # Azure OpenAI 客户端工厂
│   ├── interfaces.py       # Protocol 接口定义
│   └── logger.py           # 统一日志
├── tests/                  # 测试用例（120+）
└── assets/sounds/          # 提示音文件
```

## 开发

```powershell
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行所有测试
python -m pytest tests/ -v
```

## 常见问题

**快捷键不生效**
- 确认没有其他程序占用 `Alt+Z`
- 可在设置窗口中录制新的快捷键

**粘贴时目标应用没反应**
- 部分以管理员权限运行的程序可能无法接收模拟按键
- 尝试以管理员身份运行 VoxAI

**API 调用超时**
- 默认超时 60 秒，检查网络连接和 Azure 服务状态
- 如在企业网络中，确认代理设置正确

**录音太短被跳过**
- 录音不足 0.3 秒会被视为误触而跳过

**sounddevice 安装失败**
- `sounddevice` 的 pip 包通常自带 PortAudio，如果报错可尝试：
  ```powershell
  pip install sounddevice --force-reinstall
  ```

## 技术栈

- **语言**: Python 3.10+
- **语音转写**: Azure OpenAI (gpt-4o-mini-transcribe / Whisper)
- **文字润色**: Azure OpenAI (GPT-4o-mini)
- **热键监听**: pynput
- **录音**: sounddevice + soundfile
- **UI**: tkinter (设置窗口) + pystray (系统托盘)
- **剪贴板**: pyperclip

## License

[MIT](LICENSE)
