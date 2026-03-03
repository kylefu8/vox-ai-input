"""
主控制器模块

AIInputApp 负责协调所有子模块，管理应用的状态机：
- 空闲 → 按下热键 → 录音中 → 松开热键 → 处理中 → 空闲

线程模型：
- 主线程: pynput 键盘监听（事件循环）
- 录音: sounddevice 回调模式（音频线程，不阻塞）
- 后台处理: Whisper API → GPT API → 粘贴（daemon thread）
"""

import threading

from src.config import (
    load_config,
    get_azure_config,
    get_recording_config,
    get_hotkey_config,
    get_polish_config,
)
from src.hotkey import HotkeyListener
from src.logger import setup_logger
from src.notifier import play_start_sound, play_stop_sound, create_default_sounds
from src.output import paste_text
from src.polisher import Polisher
from src.recorder import Recorder
from src.transcriber import Transcriber
from src.tray import TrayIcon, STATE_IDLE, STATE_RECORDING, STATE_PROCESSING

log = setup_logger(__name__)


class AIInputApp:
    """
    AI 语音输入法主控制器。

    管理整个应用的生命周期和工作流程：
    1. 初始化所有子模块（录音器、转写器、润色器、热键监听器）
    2. 监听全局热键
    3. 按下热键 → 开始录音 + 播放提示音
    4. 松开热键 → 停止录音 + 启动后台处理线程
    5. 后台处理：转写 → 润色 → 粘贴
    """

    def __init__(self):
        """初始化主控制器，加载配置并创建所有子模块。"""
        log.info("=" * 50)
        log.info("AI-Input 语音输入法 — 正在启动...")
        log.info("=" * 50)

        # 加载配置
        self._config = load_config()
        azure_cfg = get_azure_config(self._config)
        rec_cfg = get_recording_config(self._config)
        hotkey_cfg = get_hotkey_config(self._config)
        polish_cfg = get_polish_config(self._config)

        # 初始化录音器
        self._recorder = Recorder(
            sample_rate=rec_cfg["sample_rate"],
            channels=rec_cfg["channels"],
            max_duration=rec_cfg["max_duration"],
        )

        # 初始化转写器
        self._transcriber = Transcriber(
            endpoint=azure_cfg["endpoint"],
            api_key=azure_cfg["api_key"],
            api_version=azure_cfg["api_version"],
            deployment=azure_cfg["whisper_deployment"],
        )

        # 初始化润色器（如果启用）
        self._polisher = None
        self._polish_enabled = polish_cfg.get("enabled", True)
        if self._polish_enabled:
            self._polisher = Polisher(
                endpoint=azure_cfg["endpoint"],
                api_key=azure_cfg["api_key"],
                api_version=azure_cfg["api_version"],
                deployment=azure_cfg["gpt_deployment"],
            )

        # 语言设置
        self._language = polish_cfg.get("language", "zh")

        # 初始化热键监听器（含取消回调）
        self._hotkey_listener = HotkeyListener(
            combination_str=hotkey_cfg["combination"],
            on_activate=self._on_hotkey_press,
            on_deactivate=self._on_hotkey_release,
            on_cancel=self._on_cancel,
        )

        # 状态锁（防止并发问题）
        self._processing_lock = threading.Lock()
        self._is_processing = False

        # 生成默认提示音文件
        create_default_sounds()

        # 初始化系统托盘图标
        self._tray = TrayIcon(on_quit=self._shutdown)

        log.info("所有模块初始化完成！")

    def run(self):
        """
        启动应用。

        这个方法会阻塞当前线程（热键监听事件循环）。
        按 Ctrl+C 退出。
        """
        # 启动系统托盘图标（后台线程）
        self._tray.start()

        log.info("")
        log.info("🎤 AI-Input 已启动！")
        log.info("长按快捷键说话，松开后文字自动粘贴到当前应用")
        log.info("录音中按 Esc 可取消当前录音")
        log.info("按 Ctrl+C 或通过托盘菜单退出程序")
        log.info("")

        try:
            self._hotkey_listener.start()
        except KeyboardInterrupt:
            self._shutdown()

    def _shutdown(self):
        """
        优雅地关闭所有模块。

        可由 Ctrl+C 或托盘退出菜单触发。
        """
        log.info("")
        log.info("程序正在退出...")
        self._hotkey_listener.stop()
        self._tray.stop()
        log.info("再见！")

    def _on_hotkey_press(self):
        """
        热键按下回调 — 开始录音。

        在热键监听线程中调用。
        """
        # 如果正在处理上一条语音，跳过
        if self._is_processing:
            log.warning("上一条语音还在处理中，请稍候...")
            return

        # 更新托盘状态为录音中
        self._tray.set_state(STATE_RECORDING)

        # 播放开始提示音
        play_start_sound()

        # 开始录音（设置自动停止回调）
        self._recorder.start(on_auto_stop=self._process_audio)

    def _on_hotkey_release(self):
        """
        热键松开回调 — 停止录音并启动后台处理。

        在热键监听线程中调用。
        """
        if not self._recorder.is_recording:
            return

        # 播放结束提示音
        play_stop_sound()

        # 停止录音
        wav_path = self._recorder.stop()
        if not wav_path:
            log.warning("没有有效的录音数据")
            return

        # 启动后台线程处理（不阻塞热键监听）
        thread = threading.Thread(
            target=self._process_audio,
            args=(wav_path,),
            daemon=True,
        )
        thread.start()

    def _on_cancel(self):
        """
        取消录音回调 — 按 Esc 时触发。

        丢弃当前录音数据，恢复空闲状态。
        在热键监听线程中调用。
        """
        if not self._recorder.is_recording:
            return

        # 停止录音但丢弃数据
        wav_path = self._recorder.stop()

        # 清理临时文件（如果产生了的话）
        if wav_path:
            self._transcriber.cleanup_audio(wav_path)

        # 恢复空闲状态
        self._tray.set_state(STATE_IDLE)
        log.info("🚫 录音已取消")

    def _process_audio(self, wav_path):
        """
        后台处理流程：转写 → 润色 → 粘贴。

        在后台 daemon 线程中执行。

        Args:
            wav_path: WAV 录音文件路径
        """
        with self._processing_lock:
            if self._is_processing:
                log.warning("已有处理任务在运行，跳过")
                return
            self._is_processing = True

        # 更新托盘状态为处理中
        self._tray.set_state(STATE_PROCESSING)

        try:
            # 1. 语音转文字
            raw_text = self._transcriber.transcribe(
                wav_path, language=self._language
            )

            # 清理临时音频文件
            self._transcriber.cleanup_audio(wav_path)

            if not raw_text:
                log.warning("转写结果为空，跳过")
                return

            # 2. AI 润色
            if self._polisher and self._polish_enabled:
                final_text = self._polisher.polish(raw_text)
            else:
                final_text = raw_text

            if not final_text:
                log.warning("润色结果为空，跳过")
                return

            # 3. 粘贴到当前应用
            log.info("🎯 最终文字: %s",
                      final_text[:80] + "..." if len(final_text) > 80 else final_text)
            paste_text(final_text)

        except Exception as e:
            log.error("处理音频时出错: %s", e)

        finally:
            with self._processing_lock:
                self._is_processing = False
            # 处理完毕，恢复空闲状态
            self._tray.set_state(STATE_IDLE)
