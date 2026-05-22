## Vox AI Input v0.0.9

### Floating UI Polish / 悬浮 UI 打磨

This release continues the floating recording experience work from v0.0.8 and focuses on the details users see every day.

本版本继续打磨 v0.0.8 引入的悬浮录音体验，重点处理用户每天都会看到的细节。

- **Sharper floating mic** — Refined collapsed, hover, recording, processing, and cancel states
- **Result preview capsule** — Rebuilt the old text preview as a matching capsule below the mic when possible
- **Stable positioning** — Dragged positions are saved as the collapsed mic position, so the capsule no longer jumps after recording
- **Theme sync** — Floating mic and result preview now follow settings light/dark theme changes, including live preview and cancel rollback
- **Clearer light theme** — Light floating capsules use a soft gray surface instead of pure white for better desktop contrast

---

- **更精致的悬浮麦克风** — 细化收起、hover、录音中、处理中和取消按钮状态
- **结果预览胶囊** — 将旧文字预览浮窗重做为同视觉体系的结果胶囊，优先显示在麦克风下方
- **位置更稳定** — 拖动位置按收起小圆坐标保存，录音结束后不再跳回或偏移
- **主题同步** — 悬浮麦克风和结果预览跟随设置窗口深浅色切换，支持实时预览和取消回滚
- **浅色更清楚** — 浅色悬浮胶囊改用浅灰表面，不再是桌面上容易看不清的纯白

### Private Gateway Compatibility / 私有网关兼容

Polishing providers can now work with trusted private gateways that are reachable only by IP or use self-signed TLS certificates.

润色 provider 现在可以兼容只能通过 IP 访问、或使用自签名 TLS 证书的可信私有网关。

- **IP/self-signed mode** — Per-profile `allow_insecure_tls` supports trusted private endpoints without changing global networking
- **Optional Host header** — `host_header` remains optional; leave it blank when the backend routes correctly by IP
- **Shared transport layer** — Model fetching, validation, OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, and Azure OpenAI all use the same transport options
- **Simpler UI wording** — Settings explains this as a private-gateway compatibility mode, not certificate management

---

- **IP/自签名兼容** — profile 级 `allow_insecure_tls` 支持可信私有端点，不影响全局网络请求
- **Host 可选** — `host_header` 继续保持可选；后端按 IP 即可路由时可以留空
- **统一传输层** — 获取模型、验证、OpenAI Chat Completions、OpenAI Responses、Anthropic Messages 和 Azure OpenAI 共用同一套连接选项
- **设置更轻量** — 设置页按“私有网关兼容”表达，不引入单独证书管理流程

### Stability / 稳定性

This release also reduces a native Windows crash risk around Tk/Tcl windows.

本版本同时收口了 Windows 上 Tk/Tcl 窗口相关的原生崩溃风险。

- **No temporary Tk update dialogs** — Update prompts now use native Windows MessageBox dialogs
- **Process-wide Tk guard** — Settings, log window, and Tk fallback overlays serialize independent Tk root lifetimes
- **Lazy log window** — The log window starts only when opened and releases Tk when closed
- **More coverage** — Added targeted tests for update dialogs, dialog routing, log window startup, settings Tk guards, floating UI rendering, and preview capsules

---

- **更新弹窗不再临时创建 Tk** — 更新检查/下载提示改用 Windows 原生 MessageBox
- **进程级 Tk 守卫** — 设置窗口、日志窗口和 Tk fallback 浮窗统一串行管理独立 Tk root 生命周期
- **日志窗口按需启动** — 日志窗口只在打开时创建，关闭后释放 Tk
- **测试覆盖增加** — 新增更新弹窗、弹窗路由、日志窗口懒启动、设置窗口 Tk 守卫、悬浮 UI 渲染和预览胶囊测试

### Verification / 验证

- `.\.venv\Scripts\python.exe -m compileall -q run.py src tests`
- `.\.venv\Scripts\python.exe -m pytest -q` — 214 tests passed

### Download / 下载

| File | Description |
|------|-------------|
| `VoxAIInput-Setup-0.0.9.exe` | **Installer** (recommended) — Double-click to install |
| `VoxAIInput-0.0.9-win64.zip` | **Portable** — Extract and run |
| `config.example.yaml` | Config template |
