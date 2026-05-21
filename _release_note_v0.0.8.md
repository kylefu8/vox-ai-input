## Vox AI Input v0.0.8

### Floating Control + Hotkey UX / 悬浮控制与快捷键体验

This release adds a second recording entry point beyond the global hotkey: a small draggable floating microphone that stays in sync with the tray icon, preview state, and hotkey workflow.

本版本新增全局快捷键之外的第二个录音入口：可拖动的屏幕悬浮麦克风按钮，并与托盘、预览状态和快捷键流程保持同步。

- **Draggable floating mic** — Click to start/stop recording; drag to save its position
- **Unified recording state** — Hotkey, tray, preview overlays, and floating control now share one start/stop/cancel path
- **Safer default hotkey** — Default recording hotkey changed from `Alt+Z` to `Ctrl+Shift+Space`
- **Conflict warnings** — Settings warns about high-risk shortcuts such as `Alt+Z`, `Win+Space`, and `Ctrl+Space`

---

- **可拖动悬浮麦克风** — 点击开始/停止录音，拖动后自动保存位置
- **统一录音状态机** — 快捷键、托盘、预览浮窗和悬浮按钮复用同一套开始/停止/取消逻辑
- **更稳妥的默认快捷键** — 默认录音快捷键从 `Alt+Z` 改为 `Ctrl+Shift+Space`
- **快捷键冲突提示** — 设置页会提示 `Alt+Z`、`Win+Space`、`Ctrl+Space` 等高风险组合

### UI Polish + Multilingual Settings / 界面打磨与多语言设置

The settings experience now supports Chinese/English UI switching, in-place light/dark theme switching, and an Info dialog that follows the active theme.

设置体验现在支持中文/英文界面切换、深浅色原地换肤，以及跟随当前配色的软件说明弹窗。

- **Chinese/English UI** — Settings and tray labels can switch between `zh-CN` and `en`
- **Theme button** — Dark/light switching moved to the top-right action area
- **Themed Info dialog** — Product description and polishing tips are available from the Info button
- **Sharper Windows rendering** — DPI awareness, bitmap action icons, and a softer dark palette improve clarity
- **Less visual flicker** — Theme switching no longer destroys and recreates the whole settings window

---

- **中英文界面** — 设置窗口和托盘菜单支持 `zh-CN` / `en`
- **主题按钮** — 深浅色切换移动到右上角操作区
- **配色适配的说明弹窗** — Info 按钮展示软件说明和润色小技巧
- **更清晰的 Windows 渲染** — DPI awareness、彩色位图按钮图标和更柔和的深色主题提升清晰度
- **减少可见闪烁** — 主题切换不再销毁并重建整个设置窗口

### Polishing API + Prompt Upgrade / 润色 API 与 Prompt 升级

Polishing setup now works better with modern OpenAI-compatible gateways and Responses-only models, while the default prompt is more useful for real speech transcripts.

润色设置现在更适配现代 OpenAI-compatible 网关和仅支持 Responses API 的模型；默认 prompt 也更适合真实语音转写文本。

- **Selectable API type** — Choose Auto Detect, OpenAI Chat Completions, OpenAI Responses, or Anthropic Messages
- **Responses API support** — Added `/v1/responses` client support for newer OpenAI-style models
- **Endpoint normalization** — Users may omit `/v1`; the resolved API base is saved as `base_url` in the background
- **Model-first workflow** — "Fetch models" now appears before validation in the Polishing settings
- **Better default prompt** — Cleans filler words, repeated fragments, mixed Chinese-English speech artifacts, and can auto-structure lists
- **Failure visibility** — If polishing fails and falls back to raw transcription, preview/history now mark that fallback clearly

---

- **API 类型可选** — 支持自动识别、OpenAI Chat Completions、OpenAI Responses、Anthropic Messages
- **支持 Responses API** — 新增 `/v1/responses` 客户端，适配较新的 OpenAI 风格模型
- **Endpoint 自动规范化** — 用户可省略 `/v1`；后台解析后的实际 API base 会保存为 `base_url`
- **先获取模型再验证** — 润色设置中“获取模型”放到验证按钮左侧
- **默认 prompt 更实用** — 清理口水词、重复片段、中英混杂语音残留，并可自动整理清单
- **润色失败可见** — 润色失败降级为原文时，预览和历史记录会明确标记

### Evaluation + Recommendations / 评测与推荐

This cycle added a local polishing evaluation harness and used it to compare common models across polishing, translation, and bilingual output scenarios.

本轮新增本地润色评测脚本，并对常见模型在润色、翻译、双语输出场景下做了对比。

- **Evaluation harness** — Added `scripts/eval_polish.py`, `eval/cases.yaml`, and baseline prompt snapshots
- **Report output** — The harness can generate JSONL, Markdown, and static HTML reports
- **Model guidance** — `gpt-5.4-mini` is the recommended balanced default; `gpt-5.5` is recommended for best quality
- **Not primary recommendations** — `gpt-5.4`, `gpt-4o`, and `gpt-4o-mini` are kept as compatible options but not recommended as defaults

---

- **评测工具链** — 新增 `scripts/eval_polish.py`、`eval/cases.yaml` 和旧 prompt 基线快照
- **报告输出** — 支持生成 JSONL、Markdown 和静态 HTML 报告
- **模型建议** — `gpt-5.4-mini` 作为综合默认推荐，`gpt-5.5` 作为质量优先推荐
- **非主推荐模型** — `gpt-5.4`、`gpt-4o`、`gpt-4o-mini` 保留兼容，但不作为默认推荐

### Verification / 验证

- `py -3.12 -m compileall -q run.py src tests`
- `pytest -q` — 176 tests passed

### Download / 下载

| File | Description |
|------|-------------|
| `VoxAIInput-Setup-0.0.8.exe` | **Installer** (recommended) — Double-click to install |
| `VoxAIInput-0.0.8-win64.zip` | **Portable** — Extract and run |
| `config.example.yaml` | Config template |
