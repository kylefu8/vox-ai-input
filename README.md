# Vox AI Input

[中文文档](README_zh.md)

**AI Voice Input** — Hold a hotkey to speak, release to auto-paste transcribed text into any app.

> 🎤 Speak → 🤖 AI Transcribe → ✨ AI Polish → 🌐 Translate (optional) → 📋 Auto-paste

Supports mixed Chinese-English recognition, spoken symbol conversion (e.g., "at sign" → @), AI-powered punctuation and grammar correction, and optional real-time translation to 9 languages.

> **v0.0.8: Floating mic + stronger polishing!** Adds a draggable recording control, Chinese/English UI, dark/light theme toggle, selectable polishing API types including OpenAI Responses, and a much stronger default speech cleanup prompt.

## Features

- **One-key voice input** — Hold hotkey to speak, release to auto-paste
- **🆕 Local offline transcription** — Powered by sherpa-onnx, no internet required, ultra-low latency
  - SenseVoice (recommended, best for Chinese, ~156MB)
  - Whisper Small (99 languages, ~610MB)
  - Paraformer Streaming (Chinese-English real-time transcription)
  - One-click model download in settings
- **AI smart polishing** — Auto-fix punctuation, remove filler words, split paragraphs, and turn spoken lists into clean numbered items
- **Multiple polishing API endpoints** — Supports OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, and OpenAI-compatible gateways
- **Floating recording control** — A draggable always-on-top mic button can start/stop recording and mirrors hotkey/tray status
- **History** — Save recent outputs, review them in settings, and copy them again
- **Mixed language recognition** — Accurately handles Chinese-English mixed speech
- **Symbol dictation** — Say "at sign" to output @, "hash" to output #
- **Real-time translation** — Speak in one language, output in another (9 languages supported)
- **Advanced prompt override** — Optional, collapsed by default for safer polishing behavior
- **Recording countdown** — Semi-transparent countdown overlay near max duration
- **Live log window** — Dark-themed scrolling log for troubleshooting
- **Modern settings UI** — Cleaner left navigation, focused pages, Chinese/English UI, and dark/light theme toggle
- **App icon** — Fluent-style blue-purple gradient microphone
- **Hotkey hot-reload** — Changes take effect immediately, no restart needed
- **System tray** — Gradient microphone icon with status colors
- **One-click updates** — Check for new GitHub releases from tray menu
- **Config hot-reload** — All setting changes take effect immediately
- **Auto-start** — Optional launch on system startup

## Requirements

- **Windows** 10/11 (x86_64)
- **Microphone** with system access granted
- **Transcription engine**: local offline model downloaded from settings
- **Optional polishing API**: Azure OpenAI / OpenAI-compatible / Anthropic

## Quick Start

### Option 1: Installer (Recommended)

1. Download `VoxAIInput-Setup-x.x.x.exe` from [Releases](https://github.com/kylefu8/vox-ai-input/releases)
2. Run the installer (supports desktop shortcut + auto-start options)
3. On first launch, a settings window opens — download a local model and optionally configure AI polishing
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
| **Click floating mic** | Start/stop recording, synced with hotkey status |
| **Drag floating mic** | Move it; position is saved automatically |
| **Press Esc while recording** | Cancel current recording |
| **Tray right-click → Settings** | Open settings window |
| **Settings top right → Interface/Theme/Info** | Switch UI language, toggle theme, and view app info |
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
| `python run.py --open-settings` | Start the app and open Settings immediately |
| `python run.py --version` | Show version |

## Configuration

Edit `config.yaml` (or configure via the settings window on first launch):

| Key | Description | Default |
|-----|-------------|---------|
| `ui.language` | Settings/tray UI language: `zh-CN` / `en` | `zh-CN` |
| `ui.theme` | Settings color theme: `dark` / `light` | `dark` |
| `ui.floating_control.enabled` | Show the draggable floating mic button | `true` |
| `stt.backend` | Transcription engine, fixed to local offline | `local` |
| `stt.model_type` | Local model: `sense_voice`, `whisper_small`, or `paraformer_streaming` | `sense_voice` |
| `recording.sample_rate` | Sample rate (Hz) | `16000` |
| `recording.channels` | Audio channels | `1` |
| `recording.max_duration` | Max recording duration (seconds) | `60` |
| `hotkey.combination` | Recording hotkey | `ctrl+shift+space` |
| `polish.enabled` | Enable AI polishing | `false` |
| `polish.profile` | LLM profile used for polishing | `default` |
| `polish.translate_to` | Translation target language code (empty = none) | `""` |
| `polish.show_original` | When translating, also output the polished source text | `false` |
| `llm_profiles.default.provider` | API type: `auto`, `openai_compatible`, `openai_responses`, or `anthropic` | `auto` |
| `llm_profiles.default.endpoint` | Polishing API endpoint | `""` |
| `llm_profiles.default.base_url` | Optional resolved runtime API base, usually auto-filled from endpoint | unset |
| `llm_profiles.default.api_key` | Polishing API key | `""` |
| `llm_profiles.default.model` | Model name | `""` |
| `history.enabled` | Save recent output history | `true` |
| `history.max_entries` | Maximum retained history entries | `100` |

### Polishing API Setup

In Settings, the Polishing page asks for API Type, Endpoint, API Key, and Model. Use `OpenAI Chat Completions` for `/v1/chat/completions`, `OpenAI Responses` for `/v1/responses`, or `Anthropic Messages` for `/v1/messages`; `Auto Detect` is still available. "Fetch models" tries to load model names from the endpoint and can resolve a missing `/v1` in the background. The UI keeps the endpoint you typed; the resolved API base is saved as `base_url` and used at runtime. You can also edit YAML directly:

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
│   ├── voice_pipeline.py   # Core transcribe → polish → output workflow
│   ├── runtime_components.py # Runtime component factories
│   ├── config.py           # Config loading, saving, validation
│   ├── recorder.py         # Microphone recording + device detection
│   ├── audio_files.py      # Temporary audio file utilities
│   ├── local_transcriber.py # Local offline STT (sherpa-onnx)
│   ├── model_manager.py    # Local model download & management
│   ├── polisher.py         # AI text polishing + translation
│   ├── llm_clients.py      # Polishing LLM adapters (Azure/OpenAI-compatible/Anthropic)
│   ├── hotkey.py           # Global hotkey listener
│   ├── output.py           # Clipboard + simulated paste
│   ├── tray.py             # System tray (gradient microphone icon)
│   ├── floating_control.py # Draggable on-screen recording button
│   ├── i18n.py             # Lightweight Chinese/English UI strings
│   ├── settings_window.py  # Settings window with dark/light themes
│   ├── log_window.py       # Live log viewer
│   ├── countdown.py        # Recording countdown overlay (Win32 Layered Window)
│   ├── updater.py          # GitHub version check & update
│   ├── notifier.py         # Sound notifications
│   ├── autostart.py        # Auto-start management
│   ├── azure_client.py     # Azure OpenAI client factory
│   ├── paths.py            # Path utilities (compatible with packaged/source modes)
│   ├── interfaces.py       # Protocol interface definitions
│   └── logger.py           # Unified logging (UTF-8 safe)
├── tests/                  # 170+ test cases
├── models/                 # Local STT models (user downloads on demand, not in git)
├── assets/sounds/          # Recording notification sounds
├── scripts/                # Build helper scripts
└── .github/workflows/      # GitHub Actions CI/CD
```

## Development

```powershell
# First-time setup on a new machine
.\scripts\bootstrap_dev.ps1

# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests
python -m pytest tests/ -v

# Local build
pip install pyinstaller pyinstaller-hooks-contrib
pyinstaller build.spec --clean --noconfirm
# Output in dist/VoxAIInput/
```

### Codex Multi-Machine Development

This repo includes `AGENTS.md` as persistent project context for fresh Codex sessions. For a clean machine or two-computer workflow, see `docs/codex-sync.md`; for copyable Codex entry prompts, see `docs/codex-entry-prompts.md`; for the bootstrap script itself, see `docs/bootstrap-dev.md`.

## FAQ

**Hotkey not working**
- Make sure no other app is using the same hotkey
- Tray right-click → Settings → Record a new hotkey, save to apply immediately

**Paste not working in target app**
- Some apps running with admin privileges may block simulated keystrokes
- Try running Vox AI Input as administrator

**Translation not working**
- Confirm a target language is selected in settings and saved
- Check the prompt in Polishing settings; clear it to restore the default prompt if needed

**Cannot record via RDP**
- RDP does not forward the microphone by default — in the RDP client: Local Resources → Remote Audio → Settings → enable "Record from this computer"

**Recording too short, skipped**
- Recordings shorter than 0.3 seconds are treated as accidental triggers and skipped

## Tech Stack

- **Language**: Python 3.10+
- **Speech-to-text**: Local sherpa-onnx (SenseVoice / Whisper Small / Paraformer)
- **Text polishing + translation**: Azure OpenAI / OpenAI-compatible / Anthropic
- **Hotkey listener**: pynput
- **Recording**: sounddevice + soundfile
- **UI**: tkinter (settings, log window, floating control) + pystray (system tray)
- **Countdown overlay**: Win32 Layered Window (per-pixel alpha transparency)
- **Packaging**: PyInstaller (--onedir) + Inno Setup (installer)
- **CI/CD**: GitHub Actions

## License

[MIT](LICENSE)
