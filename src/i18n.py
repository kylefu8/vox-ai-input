"""
Lightweight UI internationalization helpers.

The app is still small enough that a source-text dictionary is easier to
maintain than a full locale framework. Chinese remains the source language;
missing translations fall back to the original Chinese text.
"""

DEFAULT_UI_LANGUAGE = "zh-CN"
SUPPORTED_UI_LANGUAGES = ("zh-CN", "en")

_LANGUAGE_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_hans": "zh-CN",
    "zh-hans": "zh-CN",
    "cn": "zh-CN",
    "chinese": "zh-CN",
    "简体中文": "zh-CN",
    "en": "en",
    "en-us": "en",
    "en-gb": "en",
    "english": "en",
}

_LANGUAGE_LABELS = {
    "zh-CN": {
        "zh-CN": "简体中文",
        "en": "English",
    },
    "en": {
        "zh-CN": "Chinese",
        "en": "English",
    },
}

_EN = {
    "Vox AI Input — 空闲": "Vox AI Input — Idle",
    "Vox AI Input — 录音中...": "Vox AI Input — Recording...",
    "Vox AI Input — 处理中...": "Vox AI Input — Processing...",
    "点击录音": "Record",
    "处理中": "Working",
    "设置": "Settings",
    "历史记录": "History",
    "日志": "Logs",
    "检查更新": "Check for Updates",
    "退出": "Quit",
    "转写": "Transcribe",
    "本地模型": "Local Model",
    "本地离线转写模型设置": "Local offline transcription model settings",
    "润色": "Polish",
    "AI API": "AI API",
    "润色、翻译和 LLM 配置": "Polish, translation, and LLM settings",
    "操作": "Actions",
    "快捷键": "Hotkey",
    "触发按键和启动行为": "Trigger key and startup behavior",
    "数据": "Data",
    "历史浏览与复制": "Browse and copy recent outputs",
    "连接": "Connection",
    "历史": "History",
    "选择本地语音识别模型。": "Choose the local speech recognition model.",
    "配置可选 AI 润色连接和翻译输出。": "Configure optional AI polishing and translation output.",
    "设置长按录音快捷键和启动行为。": "Configure push-to-talk and startup behavior.",
    "查看、复制和清理最近输出。": "Review, copy, and clear recent outputs.",
    "转写引擎": "Transcription Engine",
    "固定使用本地模型，云端 API 只用于可选润色。": "Always use local models; cloud APIs are only for optional polishing.",
    "本地转写": "Local Transcription",
    "无在线转录": "No Online STT",
    "已就绪": "Ready",
    "下载": "Download",
    "删除": "Delete",
    "润色 API": "Polishing API",
    "只保留连接所需字段，验证时自动识别 API 类型。": "Only connection fields are required; validation detects the API type.",
    "连接状态": "Connection",
    "未验证": "Unverified",
    "API 类型": "API Type",
    "自动识别": "Auto Detect",
    "Endpoint": "Endpoint",
    "API Key": "API Key",
    "模型": "Model",
    "验证会依次尝试 OpenAI-compatible、Azure OpenAI 和 Anthropic，并把可用类型写回配置。": "Validation tries OpenAI-compatible, Azure OpenAI, and Anthropic, then saves the working type.",
    "验证并识别": "Validate",
    "获取模型": "Fetch",
    "显示": "Show",
    "隐藏": "Hide",
    "验证成功": "Validation Succeeded",
    "验证失败": "Validation Failed",
    "润色 API 验证成功。类型：{provider}。返回：{preview}": "Polishing API validated. Type: {provider}. Response: {preview}",
    "正在自动识别 API 类型...": "Detecting API type...",
    "正在验证 API 连接...": "Validating API connection...",
    "正在获取模型列表...": "Fetching model list...",
    "获取失败": "Fetch Failed",
    "未获取到模型": "No Models Found",
    "模型列表": "Model List",
    "已识别：{provider}": "Detected: {provider}",
    "润色流程": "Polishing Flow",
    "控制是否调用 AI，以及是否把结果翻译为其他语言。": "Control whether AI is called and whether output is translated.",
    "启用 AI 润色": "Enable AI polishing",
    "可选": "Optional",
    "翻译": "Translate",
    "语音输入后自动翻译": "Translate after speech input",
    "翻译时同时输出原文": "Also output original text when translating",
    "高级提示词": "Advanced Prompt",
    "默认使用内置语音后处理提示词。": "Use the built-in speech post-processing prompt by default.",
    "提示词": "Prompt",
    "已自定义": "Customized",
    "默认": "Default",
    "展开": "Expand",
    "收起": "Collapse",
    "大多数情况下不需要修改；改错会让润色变得啰嗦或偏题。": "Usually leave this alone; a bad prompt can make polishing verbose or off-topic.",
    "留空=使用默认提示词": "Leave empty to use the default prompt",
    "语音小技巧": "Voice Tips",
    "可以直接说出小指令，默认润色会在不改变原意的前提下处理。": "Say small instructions naturally; default polishing will handle them without changing your meaning.",
    "说“帮我总结成要点……”会输出要点。": "Say \"summarize this into key points...\" to get bullet points.",
    "说“整理成待办……”会提取行动项。": "Say \"turn this into to-dos...\" to extract action items.",
    "说“写成一段发给同事的话……”会整理成消息。": "Say \"write this as a message to a coworker...\" to shape it as a message.",
    "包含“第一/第二/最后”等枚举时，会尽量整理成编号列表。": "When it hears enumeration such as \"first/second/finally\", it will try to make a numbered list.",
    "endpoint、base_url、Responses API 等技术词会尽量保留。": "Technical terms such as endpoint, base_url, and Responses API are preserved where possible.",
    "快捷键与启动": "Hotkey & Startup",
    "控制录音触发方式和桌面启动行为。": "Control recording trigger and startup behavior.",
    "录制": "Record",
    "取消": "Cancel",
    "按下快捷键...": "Press a hotkey...",
    "开机自启动": "Start at login",
    "显示悬浮录音按钮": "Show floating mic button",
    "可拖动": "Draggable",
    "左键开始/停止，拖动可移动；右键录音中取消，否则打开设置。": "Left-click to start/stop, drag to move. Right-click cancels while recording or opens settings.",
    "推荐：Ctrl+Shift+Space 或 Ctrl+Alt+Space。": "Recommended: Ctrl+Shift+Space or Ctrl+Alt+Space.",
    "Alt+Z 常被显卡覆盖层或录屏工具占用，建议更换。": "Alt+Z is often used by GPU overlays or screen recorders. Choose another hotkey.",
    "Win+Space 通常用于切换输入法，建议更换。": "Win+Space usually switches input methods. Choose another hotkey.",
    "Ctrl+Space 常被输入法或编辑器占用，建议更换。": "Ctrl+Space is often used by IMEs or editors. Choose another hotkey.",
    "快捷键冲突": "Hotkey Conflict",
    "「{combo}」是常用系统快捷键，可能冲突。": "\"{combo}\" is a common system shortcut and may conflict.",
    "历史记录": "History",
    "最近的最终输出保存在本机，可快速复制。": "Recent final outputs are stored locally for quick copying.",
    "保存历史记录": "Save history",
    "最多保留": "Keep up to",
    "条": "items",
    "清空历史": "Clear",
    "刷新": "Refresh",
    "暂无历史记录": "No history yet",
    "完成一次语音输入后，这里会显示最近结果。": "After one voice input, recent results will appear here.",
    "复制": "Copy",
    "未润色": "Not polished",
    "润色失败": "Polish failed",
    "原文：{text}": "Original: {text}",
    "已复制到剪贴板": "Copied to clipboard",
    "历史记录已清空": "History cleared",
    "无法清空": "Cannot Clear",
    "当前没有可用的历史记录服务。": "No history service is available.",
    "清空失败": "Clear Failed",
    "无法删除历史记录文件。": "Could not delete the history file.",
    "输入错误": "Input Error",
    "保存成功": "Saved",
    "配置已保存并立即生效。": "Settings saved and applied.",
    "保存失败": "Save Failed",
    "未知错误": "Unknown error",
    "确定": "OK",
    "完成": "Done",
    "错误": "Error",
    "注意": "Notice",
    "提示": "Notice",
    "设置修改后点击保存立即生效": "Click Save to apply settings immediately",
    "保存后立即生效": "Applies after saving",
    "保存": "Save",
    "界面": "Interface",
    "切换主题": "Theme",
    "深色": "Dark",
    "浅色": "Light",
    "切换到深色": "Switch to dark",
    "切换到浅色": "Switch to light",
    "关于": "Info",
    "关于 Vox AI Input": "About Vox AI Input",
    "本地优先的语音输入工具。": "A local-first voice input tool.",
    "本地模型负责转写，AI API 只在启用润色或翻译时调用。": "Local models handle transcription; AI APIs are only used when polishing or translation is enabled.",
    "长按快捷键说话，松开后自动粘贴到当前应用。": "Hold the hotkey to speak; release to paste into the active app.",
    "支持 Azure OpenAI、OpenAI-compatible 和 Anthropic 润色端点。": "Supports Azure OpenAI, OpenAI-compatible, and Anthropic polishing endpoints.",
    "支持 OpenAI Chat、OpenAI Responses 和 Anthropic 润色端点。": "Supports OpenAI Chat, OpenAI Responses, and Anthropic polishing endpoints.",
    "项目主页": "Project",
    "打开 GitHub": "Open GitHub",
    "关闭": "Close",
    "显示 API Key": "Show API key",
    "隐藏 API Key": "Hide API key",
    "不翻译": "No translation",
    "简体中文": "Simplified Chinese",
    "英语": "English",
    "日语": "Japanese",
    "韩语": "Korean",
    "法语": "French",
    "德语": "German",
    "西班牙语": "Spanish",
    "俄语": "Russian",
    "繁体中文": "Traditional Chinese",
    "共 {count} 条历史记录": "{count} history items",
    "获取到 {count} 个模型": "{count} models found",
    "已获取 {count} 个模型/部署。": "Fetched {count} models/deployments.",
    "该 endpoint 没有暴露模型列表接口。": "This endpoint does not expose a model list API.",
    "Endpoint 不能为空": "Endpoint cannot be empty",
    "API Key 不能为空": "API Key cannot be empty",
    "润色模型名称不能为空": "Polishing model name cannot be empty",
    "历史记录保留条数必须是正整数": "History retention must be a positive integer",
    "润色 API Endpoint 不能为空": "Polishing API endpoint cannot be empty",
    "润色 API Key 不能为空": "Polishing API key cannot be empty",
    "未知模型: {model}": "Unknown model: {model}",
    "下载模型": "Download Model",
    "正在准备下载...": "Preparing download...",
    "下载完成": "Download Complete",
    "{name} 已就绪！": "{name} is ready.",
    "下载失败": "Download Failed",
    "请检查网络连接后重试。": "Check the network connection and try again.",
    "下载出错": "Download Error",
    "确认删除": "Confirm Delete",
    "确认删除模型？": "Delete this model?",
    "将删除 {name} 的所有文件。\n如需使用本地转写需重新下载。": "All files for {name} will be removed.\nDownload it again to use local transcription.",
    "删除完成": "Delete Complete",
    "{name} 已删除。": "{name} has been deleted.",
    "删除失败": "Delete Failed",
    "请关闭可能占用模型文件的程序后重试。": "Close programs that may be using the model files, then try again.",
}


def normalize_ui_language(value):
    """Return a supported UI language code."""
    raw = str(value or "").strip()
    if raw in SUPPORTED_UI_LANGUAGES:
        return raw
    alias = _LANGUAGE_ALIASES.get(raw.lower())
    return alias if alias in SUPPORTED_UI_LANGUAGES else DEFAULT_UI_LANGUAGE


def language_label(code, display_language=None):
    """Return a localized display label for a UI language code."""
    code = normalize_ui_language(code)
    display_language = normalize_ui_language(display_language or code)
    return _LANGUAGE_LABELS.get(display_language, _LANGUAGE_LABELS[DEFAULT_UI_LANGUAGE]).get(code, code)


def language_options(display_language=None):
    """Return [(label, code), ...] for language selectors."""
    display_language = normalize_ui_language(display_language)
    return [(language_label(code, display_language), code) for code in SUPPORTED_UI_LANGUAGES]


def t(text, language=None, **kwargs):
    """Translate source Chinese UI text to the selected language."""
    language = normalize_ui_language(language)
    translated = text if language == DEFAULT_UI_LANGUAGE else _EN.get(text, text)
    if kwargs:
        try:
            return translated.format(**kwargs)
        except Exception:
            return translated
    return translated
