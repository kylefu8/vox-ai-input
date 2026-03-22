# Vox AI Input

[中文文档](README_zh.md)

**AI Voice Input** — Hold a hotkey to speak, release to auto-paste transcribed text into any app.

> 🎤 Speak → 🤖 AI Transcribe → ✨ AI Polish → 🌐 Translate (optional) → 📋 Auto-paste

Supports mixed Chinese-English recognition, spoken symbol conversion (e.g., "at sign" → @), AI-powered punctuation and grammar correction, and optional real-time translation to 9 languages.

> **v0.0.6: Streaming real-time transcription + polishing model upgrade!** New Paraformer streaming model for live speech-to-text (words appear as you speak). Polishing model upgraded from gpt-4o-mini to gpt-5.4-nano — faster, cheaper, and no longer answers questions or refuses requests.

## Features

- **One-key voice input** — Hold hotkey to speak, release to auto-paste
- **🆕 Local offline transcription** — Powered by sherpa-onnx, no internet required, ultra-low latency
  - SenseVoice (recommended, best for Chinese, ~156MB)
  - Whisper Small (99 languages, ~610MB)
  - One-click model download in settings, switch between Azure / local anytime
- **AI smart polishing** — Auto-fix punctuation, grammar, remove filler words
- **Mixed language recognition** — Accurately handles Chinese-English mixed speech
- **Symbol dictation** — Say "at sign" to output @, "hash" to output #
- **Real-time translation** — Speak in one language, output in another (9 languages supported)
- **Custom prompt** — Edit polishing prompt in advanced settings
- **Recording countdown** — Semi-transparent countdown overlay near max duration
- **Live log window** — Dark-themed scrolling log for troubleshooting
- **Modern settings UI** — Dark/light theme toggle, card-based layout
- **App icon** — Fluent-style blue-purple gradient microphone
- **Hotkey hot-reload** — Changes take effect immediately, no restart needed
- **System tray** — Gradient microphone icon with status colors
- **One-click updates** — Check for new GitHub releases from tray menu
- **Config hot-reload** — All setting changes take effect immediately
- **Auto-start** — Optional launch on system startup

## Requirements

- **Windows** 10/11 (x86_64)
- **Microphone** with system access granted
- **Transcription engine** (choose one):
  - 🖥️ **Local offline** — No extra setup needed, download model in settings
  - ☁️ **Azure cloud** — Requires [Azure AI Foundry](https://ai.azure.com/) with `gpt-4o-mini-transcribe` + `gpt-4o-mini` deployed

## Quick Start

### Option 1: Installer (Recommended)

1. Download `VoxAIInput-Setup-x.x.x.exe` from [Releases](https://github.com/kylefu8/vox-ai-input/releases)
2. Run the installer (supports desktop shortcut + auto-start options)
3. On first launch, a settings window opens — fill in Azure API info or choose local transcription
4. Hold the hotkey and start speaking

### Option 2: Portable

1. Download `VoxAIInput-x.x.x-win64.zip`
2. Extract to any directory
3. Copy `config.example.yaml` to `config.yaml`, fill in your settings
4. Double-click `VoxAIInput.exe`

### Option 3: From Source

```powershell
# Clone
git clone https://github.com/kylefu8/vox-ai-input.git
cd vox-ai-input

# Virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure
Copy-Item config.example.yaml config.yaml
# Edit config.yaml with your settings

# Run
python run.py
```

## Usage

| Action | Description |
|--------|-------------|
| **Hold hotkey** | Start recording (tray icon turns red) |
| **Release hotkey** | Stop recording → transcribe → polish → paste |
| **Press Esc while recording** | Cancel current recording |
| **Tray right-click → Settings** | Open settings window |
| **Tray right-click → Log** | Open live log window |
| **Tray right-click → Check Updates** | Check for new GitHub releases |

### Tray Icon Status

| Color | Status |
|-------|--------|
| Blue-gray | Idle, waiting for input |
| Red | Recording |
| Gold | Processing (transcribing + polishing) |

### Translation

Select a target language in the settings window under "Common Settings":

| Language | Code |
|----------|------|
| No translation | (default) |
| Simplified Chinese / Traditional Chinese | zh / zh-TW |
| English / Japanese / Korean | en / ja / ko |
| French / German / Spanish / Russian | fr / de / es / ru |

Speech is automatically polished + translated in a single API call.

### CLI Arguments

| Argument | Description |
|----------|-------------|
| `python run.py` | Normal mode (tray) |
| `python run.py --test` | Test mode (press Enter to control recording) |
| `python run.py --visible` | Normal mode + keep console (for debugging) |
| `python run.py --version` | Show version |

## Configuration

Edit `config.yaml` (or configure via the settings window on first launch):

| Key | Description | Default |
|-----|-------------|---------|
| `stt.backend` | Transcription engine: `azure` (cloud) or `local` (offline) | `azure` |
| `stt.model_type` | Local model: `sense_voice` or `whisper_small` | `sense_voice` |
| `stt.num_threads` | Local inference threads | `4` |
| `azure.endpoint` | Azure OpenAI endpoint URL | *required for cloud* |
| `azure.api_key` | Azure OpenAI API Key | *required for cloud* |
| `azure.api_version` | API version | `2025-01-01-preview` |
| `azure.whisper_deployment` | Whisper model deployment name | `whisper` |
| `azure.gpt_deployment` | GPT model deployment name | `gpt-4o-mini` |
| `recording.sample_rate` | Sample rate (Hz) | `16000` |
| `recording.channels` | Audio channels | `1` |
| `recording.max_duration` | Max recording duration (seconds) | `60` |
| `hotkey.combination` | Recording hotkey | `alt+z` |
| `polish.enabled` | Enable AI polishing | `true` |
| `polish.language` | Recognition language (empty = auto-detect) | `""` |
| `polish.translate_to` | Translation target language code (empty = none) | `""` |
| `polish.system_prompt` | Custom polishing prompt (empty = default) | `""` |

## Project Structure

```
vox-ai-input/
├── run.py                  # Entry point
├── build.spec              # PyInstaller config (--onedir)
├── installer.iss           # Inno Setup installer script
├── config.example.yaml     # Config template
├── requirements.txt        # Runtime dependencies
├── src/
│   ├── app.py              # Main controller
│   ├── config.py           # Config loading, saving, validation
│   ├── recorder.py         # Microphone recording + device detection
│   ├── transcriber.py      # Azure speech-to-text
│   ├── local_transcriber.py # Local offline STT (sherpa-onnx)
│   ├── model_manager.py    # Local model download & management
│   ├── polisher.py         # AI text polishing + translation
│   ├── hotkey.py           # Global hotkey listener
│   ├── output.py           # Clipboard + simulated paste
│   ├── tray.py             # System tray (gradient microphone icon)
│   ├── settings_window.py  # Dark-themed settings window
│   ├── log_window.py       # Live log viewer
│   ├── countdown.py        # Recording countdown overlay (Win32 Layered Window)
│   ├── updater.py          # GitHub version check & update
│   ├── notifier.py         # Sound notifications
│   ├── autostart.py        # Auto-start management
│   ├── azure_client.py     # Azure OpenAI client factory
│   ├── paths.py            # Path utilities (compatible with packaged/source modes)
│   ├── interfaces.py       # Protocol interface definitions
│   └── logger.py           # Unified logging (UTF-8 safe)
├── tests/                  # 120+ test cases
├── models/                 # Local STT models (user downloads on demand, not in git)
├── assets/sounds/          # Recording notification sounds
├── scripts/                # Build helper scripts
└── .github/workflows/      # GitHub Actions CI/CD
```

## Development

```powershell
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/ -v

# Local build
pip install pyinstaller pyinstaller-hooks-contrib
pyinstaller build.spec --clean --noconfirm
# Output in dist/VoxAIInput/
```

## FAQ

**Hotkey not working**
- Make sure no other app is using the same hotkey
- Tray right-click → Settings → Record a new hotkey, save to apply immediately

**Paste not working in target app**
- Some apps running with admin privileges may block simulated keystrokes
- Try running Vox AI Input as administrator

**Translation not working**
- Confirm a target language is selected in settings and saved
- Expand advanced settings to check if the translation instruction appears in the prompt

**Cannot record via RDP**
- RDP does not forward the microphone by default — in the RDP client: Local Resources → Remote Audio → Settings → enable "Record from this computer"

**Recording too short, skipped**
- Recordings shorter than 0.3 seconds are treated as accidental triggers and skipped

## Tech Stack

- **Language**: Python 3.10+
- **Speech-to-text**: Local sherpa-onnx (SenseVoice / Whisper Small) or Azure AI Foundry (gpt-4o-mini-transcribe)
- **Text polishing + translation**: Azure AI Foundry (gpt-4o-mini)
- **Hotkey listener**: pynput
- **Recording**: sounddevice + soundfile
- **UI**: tkinter (dark-themed settings + log windows) + pystray (system tray)
- **Countdown overlay**: Win32 Layered Window (per-pixel alpha transparency)
- **Packaging**: PyInstaller (--onedir) + Inno Setup (installer)
- **CI/CD**: GitHub Actions

## License

[MIT](LICENSE)
