# AI-Input

AI 语音输入法 — 长按快捷键说话，松开后文字自动粘贴到当前应用。

## 工作原理

```
长按快捷键 → 麦克风录音 → Azure Whisper 语音转文字 → GPT 润色 → 自动粘贴
```

录音中按 **Esc** 可随时取消。系统托盘图标实时显示当前状态：

| 颜色 | 状态 |
|------|------|
| 灰色 | 空闲，等待输入 |
| 红色 | 录音中 |
| 黄色 | 处理中（转写 + 润色） |

## 环境要求

- **Python** 3.10+
- **操作系统** macOS (ARM64) 或 Windows (x86_64)
- **Azure OpenAI** 需要已部署 Whisper 和 GPT 模型
- **麦克风** 系统已授权访问

## 安装

```bash
# 1. 克隆项目
git clone <repo-url>
cd AI-Input

# 2. 创建虚拟环境
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# 3. 安装依赖
pip install -r requirements.txt

# 如果需要运行测试，安装开发依赖
pip install -r requirements-dev.txt

# 4. 配置 Azure API
# macOS / Linux
cp config.example.yaml config.yaml

# Windows (PowerShell)
Copy-Item config.example.yaml config.yaml

# 编辑 config.yaml，填入你的 Azure 端点和 API Key
```

## 使用方法

### 正常模式

```bash
python run.py
```

启动后：
1. 长按 `Ctrl+Shift+Space`（默认快捷键）开始说话
2. 松开快捷键，等待处理
3. 文字自动粘贴到当前光标位置

通过系统托盘图标的右键菜单或 `Ctrl+C` 退出。

### 测试模式

```bash
python run.py --test
```

用回车键控制录音，方便在终端中调试，无需热键：
1. 按回车 → 开始录音
2. 再按回车 → 停止录音 → 转写 → 润色 → 粘贴

### 调试日志

通过环境变量 `AI_INPUT_LOG_LEVEL` 控制日志详细程度：

```bash
# 显示详细调试信息
AI_INPUT_LOG_LEVEL=DEBUG python run.py

# Windows PowerShell
$env:AI_INPUT_LOG_LEVEL="DEBUG"; python run.py
```

支持的级别：`DEBUG`、`INFO`（默认）、`WARNING`、`ERROR`

## 配置说明

编辑 `config.yaml`（从 `config.example.yaml` 复制）：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `azure.endpoint` | Azure OpenAI 端点 URL | *必填* |
| `azure.api_key` | Azure OpenAI API Key | *必填* |
| `azure.api_version` | API 版本 | `2024-06-01` |
| `azure.whisper_deployment` | Whisper 模型部署名 | `whisper` |
| `azure.gpt_deployment` | GPT 模型部署名 | `gpt-4o-mini` |
| `recording.sample_rate` | 采样率 (Hz) | `16000` |
| `recording.channels` | 声道数 | `1` |
| `recording.max_duration` | 最长录音秒数 | `60` |
| `hotkey.combination` | 录音快捷键 | `ctrl+shift+space` |
| `polish.enabled` | 是否启用 GPT 润色 | `true` |
| `polish.language` | 语音语言代码（留空自动检测） | `zh` |

## 项目结构

```
AI-Input/
├── run.py                  # 程序入口
├── config.example.yaml     # 配置模板
├── requirements.txt        # 运行依赖
├── requirements-dev.txt    # 开发依赖（含 pytest）
├── src/
│   ├── app.py              # 主控制器，协调所有模块
│   ├── config.py           # 配置加载与验证
│   ├── hotkey.py           # 全局热键监听
│   ├── recorder.py         # 麦克风录音
│   ├── transcriber.py      # Azure Whisper 语音转文字
│   ├── polisher.py         # Azure GPT 文字润色
│   ├── output.py           # 剪贴板粘贴
│   ├── notifier.py         # 提示音播放
│   ├── tray.py             # 系统托盘图标
│   ├── azure_client.py     # Azure OpenAI 客户端工厂
│   ├── interfaces.py       # Protocol 接口定义
│   └── logger.py           # 统一日志
├── tests/                  # 测试用例
└── assets/sounds/          # 提示音文件
```

## 常见问题

### macOS

**"pynput 无法监听键盘"**
- 打开 **系统设置 → 隐私与安全性 → 辅助功能**
- 将终端应用（Terminal / iTerm2）或 Python 添加到允许列表
- 如果通过 IDE 运行，需要授权该 IDE

**"无法访问麦克风"**
- 打开 **系统设置 → 隐私与安全性 → 麦克风**
- 确认终端应用或 Python 已获授权

**"托盘图标不显示"**
- macOS 上 `pystray` 需要 `pyobjc` 支持，如果缺失可尝试：
  ```bash
  pip install pyobjc-framework-Cocoa
  ```
- 托盘图标是可选功能，即使不显示也不影响核心录音和粘贴

### Windows

**"快捷键不生效"**
- 确认没有其他程序占用了相同的快捷键组合
- 以管理员身份运行可能有助于解决权限问题

**"粘贴时目标应用没反应"**
- 部分应用（如某些管理员权限运行的程序）可能无法接收模拟按键
- 尝试以管理员身份运行 AI-Input

**"sounddevice 安装失败"**
- Windows 上需要 PortAudio。`sounddevice` 的 pip 包通常自带，如果报错可尝试：
  ```bash
  pip install sounddevice --force-reinstall
  ```

### 通用

**"API 调用超时"**
- Whisper API 超时设为 60 秒，GPT 超时设为 30 秒
- 检查网络连接和 Azure 服务状态
- 如在企业网络中，确认代理设置正确

**"录音太短被跳过"**
- 录音不足 0.3 秒会被视为误触而跳过
- 请确保说话时间足够长

## 运行测试

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行所有测试
python -m pytest tests/ -v
```
