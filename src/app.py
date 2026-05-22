"""
主控制器模块

AIInputApp 负责协调所有子模块，管理应用的状态机：
- 空闲 → 按下热键 → 录音中 → 松开热键 → 处理中 → 空闲

线程模型：
- 主线程: pynput 键盘监听（事件循环）
- 录音: sounddevice 回调模式（音频线程，不阻塞）
- 后台处理: 转写 → 润色 → 粘贴（daemon thread）
- 预览浮窗: 独立 tkinter 线程（queue 通信）
- 流式解码: 独立线程（从音频 queue 取 chunk 解码）
"""

import threading
import time
from typing import Optional

from src.config import (
    load_config,
    save_config,
    get_recording_config,
    get_hotkey_config,
    get_history_config,
    get_polish_config,
    get_stt_config,
    get_ui_config,
    get_floating_control_config,
    get_preview_overlay_config,
)
from src.hotkey import HotkeyListener
from src.history import HistoryStore
from src.interfaces import TranscriberProtocol, PolisherProtocol
from src.logger import setup_logger
from src.notifier import play_start_sound, play_stop_sound, create_default_sounds
from src.output import paste_text
from src.countdown import CountdownOverlay
from src.debug_trace import trace_floating_state
from src.preview_overlay import PreviewOverlay
from src.floating_control import FloatingControl
from src.log_window import LogWindow
from src.recorder import check_audio_input
from src.runtime_components import create_polisher, create_recorder, create_transcriber_runtime
from src.updater import Updater
from src.settings_window import open_settings
from src.audio_files import cleanup_audio
from src.tray import TrayIcon, STATE_IDLE, STATE_RECORDING, STATE_PROCESSING
from src.ui_theme import normalize_ui_theme
from src.dialogs import ask_yes_no, show_error, show_info
from src.voice_pipeline import VoicePipeline

log = setup_logger(__name__)


class _DisabledPreviewOverlay:
    """No-op replacement when the result preview capsule is disabled."""

    def configure(self, theme=None, anchor_provider=None):
        pass

    def show(self, text="", status=""):
        pass

    def update_text(self, text, status=""):
        pass

    def dismiss(self):
        pass


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
        log.info("Vox AI Input 语音输入法 — 正在启动...")
        log.info("=" * 50)

        # 检查是否首次启动或配置尚未完成
        import builtins
        self._need_setup = getattr(builtins, "_VOX_NEED_SETUP", False)

        # 加载配置
        self._config = load_config()
        rec_cfg = get_recording_config(self._config)
        hotkey_cfg = get_hotkey_config(self._config)
        polish_cfg = get_polish_config(self._config)
        ui_cfg = get_ui_config(self._config)

        # 检查麦克风是否可用（不可用则提示并退出）
        check_audio_input()

        # 初始化录音器
        self._recorder = create_recorder(rec_cfg)

        # 初始化转写器和润色器（首次启动时跳过，等用户填写 API 后通过设置窗口重建）
        self._transcriber: Optional[TranscriberProtocol] = None
        self._polisher: Optional[PolisherProtocol] = None
        self._polish_enabled = polish_cfg.get("enabled", True)
        self._language = polish_cfg.get("language", "zh")

        # 流式模式标志 + 流式转写器引用
        self._is_streaming_mode = False
        self._streaming_transcriber = None

        if not self._need_setup:
            try:
                stt_cfg = get_stt_config(self._config)
                transcriber_runtime = create_transcriber_runtime(
                    stt_cfg=stt_cfg,
                    language=self._language,
                    on_streaming_text=self._on_streaming_text,
                )
                self._transcriber = transcriber_runtime.transcriber
                self._is_streaming_mode = transcriber_runtime.is_streaming_mode
                self._streaming_transcriber = transcriber_runtime.streaming_transcriber
                if self._polish_enabled:
                    self._polisher = create_polisher(self._config, polish_cfg)
            except Exception as e:
                log.warning("初始化转写/润色模块失败（请通过设置窗口配置）: %s", e)
                self._need_setup = True
        else:
            log.info("配置尚未完成，跳过转写/润色初始化，等待用户配置")

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

        # 程序退出事件（主线程用此等待）
        self._shutdown_event = threading.Event()

        # 生成默认提示音文件
        create_default_sounds()

        # 最近一次处理的结果（供设置窗口显示）
        self._last_result_text = ""
        self._last_result_duration = 0.0

        # 会话用量统计（让用户了解 API 调用次数）
        self._session_api_calls = 0

        # 浮窗音量条节流，避免音频回调线程把 UI 队列灌满
        self._last_audio_level_sent_at = 0.0

        # 历史记录（便于回看、复制和后续重润色）
        self._history_store = HistoryStore.from_config(get_history_config(self._config))

        # 录音倒计时浮窗
        self._countdown = CountdownOverlay()

        # 结果预览胶囊；与悬浮录音按钮保持同一套视觉语言
        self._preview = self._create_preview_overlay(self._config)

        # 屏幕悬浮录音按钮（可拖动；与热键/托盘共用同一状态）
        floating_cfg = get_floating_control_config(self._config)
        self._floating = FloatingControl(
            enabled=floating_cfg["enabled"],
            x=floating_cfg["x"],
            y=floating_cfg["y"],
            theme=ui_cfg["theme"],
            language=ui_cfg["language"],
            on_toggle=self._on_floating_toggle,
            on_cancel=self._cancel_recording,
            on_settings=self._open_settings,
            on_position=self._on_floating_position,
        )

        # 实时日志窗口
        self._log_window = LogWindow()

        # 版本更新管理器
        self._updater = Updater()

        # 初始化系统托盘图标（带设置/日志/更新回调）
        self._tray = TrayIcon(
            on_quit=self._shutdown,
            on_settings=self._open_settings,
            on_history=self._open_history,
            on_log=self._open_log,
            on_update=self._check_update,
            language=ui_cfg["language"],
        )

        log.info("所有模块初始化完成！")

    def run(self, open_settings=False):
        """
        启动应用。

        热键监听在后台线程运行，主线程通过 Event 等待退出信号。
        按 Ctrl+C 或托盘菜单退出。
        """
        # 启动系统托盘图标（后台线程）
        self._tray.start()
        self._floating.start()

        log.info("")
        log.info("🎤 Vox AI Input 已启动！")
        log.info("长按快捷键说话，松开后文字自动粘贴到当前应用")
        log.info("录音中按 Esc 可取消当前录音")
        log.info("按 Ctrl+C 或通过托盘菜单退出程序")
        log.info("")

        if open_settings:
            log.info("启动参数要求打开设置窗口...")
            threading.Timer(0.6, self._open_settings).start()

        # 首次启动（API key 未配置）→ 自动打开设置窗口
        import builtins
        if getattr(builtins, "_VOX_NEED_SETUP", False) or self._need_setup:
            builtins._VOX_NEED_SETUP = False
            log.info("首次启动，自动打开设置窗口...")
            threading.Timer(1.0, self._open_settings).start()

        # 热键监听在后台线程启动（方便热键变更时重建）
        hotkey_thread = threading.Thread(
            target=self._hotkey_listener.start,
            daemon=True,
        )
        hotkey_thread.start()

        # 启动后 15 秒自动检查更新（静默，不弹窗）
        def _auto_check_update():
            try:
                self._updater.check_for_updates(background=False)
                if self._updater.state == "available":
                    log.info(
                        "🔔 发现新版本 v%s（当前 v%s），可在托盘菜单「检查更新」中升级",
                        self._updater.latest_version,
                        self._updater.current_version,
                    )
            except Exception:
                pass

        timer = threading.Timer(15.0, _auto_check_update)
        timer.daemon = True
        timer.start()

        try:
            # 主线程等待退出信号
            self._shutdown_event.wait()
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
        self._floating.stop()
        self._tray.stop()
        self._shutdown_event.set()  # 通知主线程退出
        log.info("再见！")

    def _create_preview_overlay(self, config):
        """Create the optional result preview capsule."""
        if get_preview_overlay_config(config)["enabled"]:
            ui_cfg = get_ui_config(config)
            return PreviewOverlay(theme=ui_cfg["theme"], anchor_provider=self._get_floating_preview_anchor)
        return _DisabledPreviewOverlay()

    def _reload_preview_overlay(self, new_config):
        """Apply preview overlay enable/disable changes without restarting."""
        enabled = get_preview_overlay_config(new_config)["enabled"]
        current_enabled = not isinstance(self._preview, _DisabledPreviewOverlay)
        if enabled == current_enabled:
            self._preview.configure(theme=get_ui_config(new_config)["theme"], anchor_provider=self._get_floating_preview_anchor)
            return
        self._preview.dismiss()
        self._preview = self._create_preview_overlay(new_config)

    def _get_floating_preview_anchor(self):
        """Return the floating mic rect so the result preview can sit nearby."""
        floating = getattr(self, "_floating", None)
        if not floating:
            return None
        return floating.get_preview_anchor_rect()

    def _on_hotkey_press(self):
        """
        热键按下回调 — 开始录音。

        在热键监听线程中调用。
        流式模式下同时启动转写会话和预览浮窗。
        """
        self._start_recording(source="hotkey")

    def _on_hotkey_release(self):
        """
        热键松开回调 — 停止录音并启动后台处理。

        在热键监听线程中调用。
        """
        self._stop_recording(source="hotkey")

    def _on_floating_toggle(self):
        """悬浮按钮点击回调 — 空闲时开始，录音时停止。"""
        if self._recorder.is_recording:
            self._stop_recording(source="floating")
            return
        self._start_recording(source="floating")

    def _set_activity_state(self, state, message=None):
        """同步托盘和悬浮按钮状态。"""
        trace_floating_state(
            "app.set_activity.enter",
            state=state,
            message=message,
            is_processing=getattr(self, "_is_processing", None),
            recorder_is_recording=getattr(getattr(self, "_recorder", None), "is_recording", None),
            floating_started=getattr(getattr(self, "_floating", None), "_started", None),
            floating_hwnd=getattr(getattr(self, "_floating", None), "_native_hwnd", None),
        )
        if hasattr(self, "_floating") and self._floating:
            try:
                self._floating.set_state(state, message=message)
                trace_floating_state(
                    "app.set_activity.floating_ok",
                    state=state,
                    seq=getattr(self._floating, "_state_seq", None),
                    floating_state=getattr(self._floating, "_state", None),
                    floating_hwnd=getattr(self._floating, "_native_hwnd", None),
                )
            except Exception as e:
                trace_floating_state("app.set_activity.floating_error", state=state, error=repr(e))
                log.debug("更新悬浮按钮状态失败: %s", e)
        try:
            self._tray.set_state(state)
            trace_floating_state("app.set_activity.tray_ok", state=state)
        except Exception as e:
            trace_floating_state("app.set_activity.tray_error", state=state, error=repr(e))
            log.debug("更新托盘状态失败: %s", e)

    def _force_idle_if_quiescent(self):
        """兜底同步：没有录音/处理时，确保悬浮 UI 回到空闲态。"""
        try:
            with self._processing_lock:
                is_processing = self._is_processing
            if self._recorder.is_recording or is_processing:
                return
            self._set_activity_state(STATE_IDLE)
        except Exception as e:
            log.debug("强制同步空闲状态失败: %s", e)

    def _on_floating_position(self, x, y):
        """保存悬浮按钮拖动后的位置。"""
        try:
            floating = self._config.setdefault("ui", {}).setdefault("floating_control", {})
            floating["x"] = int(x)
            floating["y"] = int(y)
            save_config(self._config)
        except Exception as e:
            log.debug("保存悬浮按钮位置失败: %s", e)

    def _start_recording(self, source="hotkey"):
        """统一入口：开始录音。"""
        if self._recorder.is_recording:
            log.debug("录音已经在进行中，忽略重复开始请求: %s", source)
            return

        # 如果正在处理上一条语音，跳过（加锁读取，避免竞态）
        with self._processing_lock:
            if self._is_processing:
                log.warning("上一条语音还在处理中，请稍候...")
                self._set_activity_state(STATE_PROCESSING)
                return

        # 检查转写器是否就绪（首次启动未配置 / 初始化失败时为 None）
        if not self._transcriber:
            log.warning("转写器未就绪，请先在设置中配置转写引擎")
            self._set_activity_state(STATE_IDLE, message="未就绪")
            return

        # 更新托盘和悬浮按钮状态为录音中
        self._set_activity_state(STATE_RECORDING)

        # 播放开始提示音
        play_start_sound()

        # 流式模式：先启动转写会话 + 浮窗
        on_chunk = None
        if self._is_streaming_mode and self._streaming_transcriber:
            self._streaming_transcriber.start_session()
            self._preview.show(text="", status="🎤 正在录音...")
            on_chunk = self._streaming_transcriber.feed_audio_chunk

        # 开始录音（流式模式传入 on_audio_chunk 回调）
        if not self._recorder.start(
            on_auto_stop=self._on_auto_stop,
            on_countdown=self._on_countdown_start,
            on_audio_chunk=on_chunk,
            on_level=self._on_audio_level,
        ):
            # 录音启动失败，恢复空闲状态
            log.error("录音启动失败，请检查麦克风")
            self._set_activity_state(STATE_IDLE, message="启动失败")
            self._preview.dismiss()

    def _on_audio_level(self, rms):
        """把录音 RMS 电平节流后同步给悬浮按钮。"""
        now = time.monotonic()
        if now - self._last_audio_level_sent_at < 0.04:
            return
        self._last_audio_level_sent_at = now

        try:
            level = min(1.0, max(0.0, float(rms)) * 18.0)
            if hasattr(self, "_floating") and self._floating:
                self._floating.set_audio_level(level)
        except Exception:
            pass

    def _stop_recording(self, source="hotkey"):
        """统一入口：停止录音并进入后台处理。"""
        if not self._recorder.is_recording:
            return

        # 先停止录音（释放 sounddevice 设备）
        wav_path = self._recorder.stop()
        self._finish_recording(wav_path, source=source)

    def _finish_recording(self, wav_path, source="hotkey"):
        """
        录音停止后的统一收口路径。

        流式模式：停止转写会话 → 取最终结果 → 润色 → 粘贴。
        非流式模式：显示浮窗 → 转写 → 润色 → 粘贴。
        """
        # 关闭倒计时浮窗
        self._countdown.dismiss()

        # 再播放结束提示音（此时设备已释放，避免冲突）
        play_stop_sound()

        self._set_activity_state(STATE_PROCESSING)

        if self._is_streaming_mode and self._streaming_transcriber:
            # ===== 流式模式 =====
            # 停止流式转写会话，获取最终结果
            final_streaming_text = self._streaming_transcriber.stop_session()

            if not final_streaming_text:
                log.warning("流式转写结果为空，跳过")
                self._preview.dismiss()
                self._set_activity_state(STATE_IDLE)
                if wav_path:
                    cleanup_audio(wav_path)
                return

            # 启动后台线程做润色+粘贴
            thread = threading.Thread(
                target=self._process_streaming_result,
                args=(final_streaming_text, wav_path),
                daemon=True,
            )
            thread.start()

        else:
            # ===== 非流式模式 =====
            if not wav_path:
                log.warning("没有有效的录音数据")
                self._set_activity_state(STATE_IDLE)
                return

            # 显示预览浮窗 — 转写中状态
            self._preview.show(text="", status="📡 转写中...")

            # 启动后台线程处理（不阻塞热键监听）
            thread = threading.Thread(
                target=self._process_audio,
                args=(wav_path,),
                daemon=True,
            )
            thread.start()

    def _on_auto_stop(self, wav_path):
        """
        录音达到最大时长自动停止时的回调。

        与手动松开热键的路径保持一致。
        在 Timer 线程中调用，不能直接同步执行处理（会阻塞 Timer）。

        Args:
            wav_path: 录音文件路径
        """
        self._finish_recording(wav_path, source="auto_stop")

    def _on_cancel(self):
        """
        取消录音回调 — 按 Esc 时触发。

        丢弃当前录音数据，恢复空闲状态。
        在热键监听线程中调用。
        """
        self._cancel_recording()

    def _cancel_recording(self):
        """统一入口：取消录音并丢弃当前音频。"""
        if not self._recorder.is_recording:
            return

        # 停止录音但丢弃数据
        wav_path = self._recorder.stop()

        # 关闭倒计时浮窗
        self._countdown.dismiss()

        # 关闭预览浮窗
        self._preview.dismiss()

        # 停止流式转写会话（如果正在进行）
        if self._is_streaming_mode and self._streaming_transcriber:
            try:
                self._streaming_transcriber.stop_session()
            except Exception:
                pass

        # 清理临时文件（如果产生了的话）
        if wav_path:
            cleanup_audio(wav_path)

        # 恢复空闲状态
        self._set_activity_state(STATE_IDLE, message="已取消")
        log.info("🚫 录音已取消")

    def _on_countdown_start(self, seconds):
        """
        倒计时开始回调 — 录音即将达到最大时长。

        在 Timer 线程中调用，启动屏幕右下角倒计时浮窗。

        Args:
            seconds: 剩余秒数（默认 5）
        """
        log.debug("录音剩余 %d 秒，显示倒计时", seconds)
        self._countdown.show(seconds)

    def _process_audio(self, wav_path):
        """
        后台处理流程：转写 → 润色 → 粘贴（非流式路径）。

        在后台 daemon 线程中执行。
        浮窗已在 _on_hotkey_release / _on_auto_stop 中 show。

        Args:
            wav_path: WAV 录音文件路径
        """
        with self._processing_lock:
            if self._is_processing:
                log.warning("已有处理任务在运行，跳过")
                cleanup_audio(wav_path)
                return
            self._is_processing = True

        self._set_activity_state(STATE_PROCESSING)

        try:
            pipeline = self._create_pipeline()
            result = pipeline.process_audio(
                wav_path,
                on_raw_text=self._show_pipeline_raw_text,
                on_final_text=self._show_pipeline_final_text,
            )
            trace_floating_state("app.process_audio.result", has_result=bool(result))
            if not result:
                self._preview.dismiss()
                return

            self._set_activity_state(STATE_IDLE)

            self._session_api_calls += result.api_calls
            log.info("⏱️  总处理耗时: %.1f 秒（本次会话已调用 API %d 次）",
                      result.duration, self._session_api_calls)

            self._last_result_text = result.final_text
            self._last_result_duration = result.duration
            if getattr(result, "polish_fallback", False):
                self._set_activity_state(STATE_IDLE)
                self._preview.update_text(result.final_text, status="⚠️ 润色失败，已使用原文")

            # 让用户看到结果后关闭浮窗
            time.sleep(1.0)
            self._preview.dismiss()

        except Exception as e:
            log.error("处理音频时出错: %s", e)
            self._preview.dismiss()

        finally:
            # 无论成功与否，都清理临时音频文件
            cleanup_audio(wav_path)
            with self._processing_lock:
                self._is_processing = False
            # 处理完毕，恢复空闲状态
            trace_floating_state("app.process_audio.finally_idle")
            self._set_activity_state(STATE_IDLE)
            threading.Timer(0.2, self._force_idle_if_quiescent).start()

    # ==================== 流式转写 ====================

    def _on_streaming_text(self, text):
        """
        流式解码线程中的回调 — 每次识别出新文字时调用。

        通过 queue 安全更新预览浮窗内容。

        Args:
            text: 当前累积的转写文字
        """
        self._preview.update_text(text, status="🎤 正在录音...")

    def _process_streaming_result(self, raw_text, wav_path):
        """
        流式转写完成后的处理流程：润色 → 粘贴（跳过转写步骤）。

        在后台 daemon 线程中执行。

        Args:
            raw_text: 流式转写的最终文字
            wav_path: 录音文件路径（用于清理）
        """
        with self._processing_lock:
            if self._is_processing:
                log.warning("已有处理任务在运行，跳过")
                if wav_path:
                    cleanup_audio(wav_path)
                return
            self._is_processing = True

        self._set_activity_state(STATE_PROCESSING)

        try:
            pipeline = self._create_pipeline()
            result = pipeline.process_text(
                raw_text,
                on_raw_text=self._show_pipeline_raw_text,
                on_final_text=self._show_pipeline_final_text,
            )
            trace_floating_state("app.process_streaming.result", has_result=bool(result))
            if not result:
                self._preview.dismiss()
                return

            self._set_activity_state(STATE_IDLE)

            self._session_api_calls += result.api_calls
            log.info("⏱️  总处理耗时: %.1f 秒（本次会话已调用 API %d 次）",
                      result.duration, self._session_api_calls)

            self._last_result_text = result.final_text
            self._last_result_duration = result.duration
            if getattr(result, "polish_fallback", False):
                self._set_activity_state(STATE_IDLE)
                self._preview.update_text(result.final_text, status="⚠️ 润色失败，已使用原文")

            # 让用户看到结果后关闭浮窗
            time.sleep(1.0)
            self._preview.dismiss()

        except Exception as e:
            log.error("处理流式转写结果时出错: %s", e)
            # 降级：尝试粘贴原始文字
            try:
                paste_text(raw_text)
                log.info("已降级粘贴原始流式文字")
            except Exception:
                pass
            self._preview.dismiss()

        finally:
            # 清理临时音频文件
            if wav_path:
                cleanup_audio(wav_path)
            with self._processing_lock:
                self._is_processing = False
            trace_floating_state("app.process_streaming.finally_idle")
            self._set_activity_state(STATE_IDLE)
            threading.Timer(0.2, self._force_idle_if_quiescent).start()

    def _create_pipeline(self):
        """创建当前配置下的核心语音处理流水线。"""
        stt_cfg = get_stt_config(self._config)
        polish_cfg = get_polish_config(self._config)
        history_cfg = get_history_config(self._config)
        return VoicePipeline(
            transcriber=self._transcriber,
            polisher=self._polisher,
            polish_enabled=self._polish_enabled,
            language=self._language,
            stt_counts_as_api=False,
            paste_func=paste_text,
            history_store=self._history_store if history_cfg["enabled"] else None,
            history_metadata={
                "stt_backend": stt_cfg["backend"],
                "polish_enabled": self._polish_enabled,
                "polish_profile": polish_cfg.get("profile", ""),
                "language": self._language,
            },
        )

    def _show_pipeline_raw_text(self, raw_text):
        """核心流水线产出原文后，更新预览浮窗。"""
        if self._polisher and self._polish_enabled:
            self._preview.update_text(raw_text, status="🤖 润色中...")
        else:
            self._preview.update_text(raw_text, status="✅ 完成")

    def _show_pipeline_final_text(self, final_text):
        """核心流水线产出最终文字后，更新预览浮窗。"""
        trace_floating_state("app.show_final_text.enter", text_len=len(final_text or ""))
        self._preview.update_text(final_text, status="✅ 完成")
        self._set_activity_state(STATE_IDLE)
        trace_floating_state("app.show_final_text.idle_sent")
        time.sleep(0.5)  # 短暂展示最终结果

    # ==================== 日志窗口 ====================

    def _open_log(self):
        """打开实时日志窗口（从托盘菜单触发）。"""
        self._log_window.show()

    # ==================== 历史窗口 ====================

    def _open_history(self):
        """在主设置窗口中打开历史记录页。"""
        self._open_settings(initial_page="data", initial_tab="records")

    def _clear_history(self):
        """清空历史记录。"""
        return self._history_store.clear()

    # ==================== 版本更新 ====================

    def _check_update(self):
        """检查更新（从托盘菜单触发），弹出更新对话框。"""
        threading.Thread(target=self._update_flow, daemon=True).start()

    def _update_flow(self):
        """更新流程：检查 → 提示 → 下载 → 替换。在后台线程执行。"""
        self._updater.check_for_updates(background=False)

        if self._updater.state == "up_to_date":
            show_info(
                "检查更新",
                f"已是最新版本 v{self._updater.current_version}",
            )
            return

        if self._updater.state == "error":
            show_error(
                "检查更新失败",
                self._updater.error_message,
            )
            return

        if self._updater.state != "available":
            return

        # 有新版本 → 询问用户
        from src.updater import _is_frozen

        size_kb = self._updater.download_size / 1024 if self._updater.download_size else 0
        mode = self._updater.update_mode

        if _is_frozen() and self._updater.download_url:
            msg = (
                f"发现新版本 v{self._updater.latest_version}！\n"
                f"（当前: v{self._updater.current_version}）\n\n"
            )
            if mode == "lightweight":
                msg += f"增量更新: {size_kb:.0f} KB\n"
                msg += "仅更新应用代码，无需重新安装。\n\n"
            else:
                msg += f"全量安装包: {size_kb / 1024:.1f} MB\n\n"
            msg += "是否下载并更新？"

            if ask_yes_no("发现新版本", msg):
                self._do_download_and_apply()
        else:
            # 源码模式 → 引导打开 Release 页面
            msg = (
                f"发现新版本 v{self._updater.latest_version}！\n"
                f"（当前: v{self._updater.current_version}）\n\n"
                "当前以源码模式运行，请手动更新：\n"
                "  git pull\n\n"
                "是否打开 GitHub Release 页面？"
            )
            if ask_yes_no("发现新版本", msg):
                self._updater.open_release_page()

    def _do_download_and_apply(self):
        """下载并应用更新。"""
        log.info("开始下载更新 v%s ...", self._updater.latest_version)
        self._updater.download_update(background=False)

        if self._updater.state == "error":
            show_error("下载失败", self._updater.error_message)
            return

        if self._updater.state == "ready":
            if ask_yes_no(
                "更新就绪",
                "新版本已下载完成！\n\n"
                "点击「是」将退出程序并自动更新。\n"
                "更新完成后程序会自动重新启动。",
            ):
                log.info("用户确认更新，准备替换...")
                if self._updater.apply_update():
                    # 退出当前程序，让 bat 脚本完成替换
                    self._shutdown()
                    import os
                    os._exit(0)

    # ==================== 设置窗口 ====================

    def _open_settings(self, initial_page="transcribe", initial_tab=None):
        """
        打开设置窗口（从托盘菜单触发）。

        在新线程中创建 tkinter 窗口，不阻塞当前线程。
        """
        open_settings(
            current_config=self._config,
            on_save=self._reload_config,
            on_clear_history=self._clear_history,
            on_get_history_entries=lambda: [
                entry.to_dict()
                for entry in self._history_store.list_recent()
            ],
            initial_page=initial_page,
            initial_tab=initial_tab,
            on_theme_change=self._apply_runtime_theme,
        )

    def _apply_runtime_theme(self, theme):
        """Apply a theme preview to always-on UI without persisting config."""
        theme = normalize_ui_theme(theme)
        language = get_ui_config(self._config)["language"]
        try:
            if hasattr(self, "_preview") and self._preview:
                self._preview.configure(theme=theme, anchor_provider=self._get_floating_preview_anchor)
        except Exception as e:
            log.debug("更新预览胶囊主题失败: %s", e)
        try:
            if hasattr(self, "_floating") and self._floating:
                self._floating.configure(theme=theme, language=language)
        except Exception as e:
            log.debug("更新悬浮按钮主题失败: %s", e)

    def _reload_config(self, new_config):
        """
        保存新配置并热重载受影响的模块。

        Args:
            new_config: 新的完整配置字典

        Returns:
            tuple: (bool, str) — 是否成功及提示消息
        """
        import src.azure_client

        try:
            # 1. 保存到文件
            save_config(new_config)

            # 2. 清除 Azure LLM 客户端缓存（下次调用时自动重建）
            src.azure_client._client_cache.clear()
            log.info("已清除 Azure LLM 客户端缓存")

            # 3. 提取各部分配置
            rec_cfg = get_recording_config(new_config)
            polish_cfg = get_polish_config(new_config)
            stt_cfg = get_stt_config(new_config)
            history_cfg = get_history_config(new_config)
            ui_cfg = get_ui_config(new_config)

            # 4. 卸载旧的本地模型（如果有 unload 方法）
            if hasattr(self._transcriber, 'unload'):
                try:
                    self._transcriber.unload()
                except Exception as e:
                    log.warning("卸载旧转写模型失败: %s", e)

            # 同时卸载流式转写器（如果存在且与 _transcriber 不同）
            if (self._streaming_transcriber
                    and self._streaming_transcriber is not self._transcriber
                    and hasattr(self._streaming_transcriber, 'unload')):
                try:
                    self._streaming_transcriber.unload()
                except Exception as e:
                    log.warning("卸载旧流式转写模型失败: %s", e)

            # 5. 更新语言设置（必须在重建转写器之前）
            self._language = polish_cfg.get("language", "zh")

            # 6. 用共享工厂重建本地转写器（同时返回流式模式信息）
            transcriber_runtime = create_transcriber_runtime(
                stt_cfg=stt_cfg,
                language=self._language,
                on_streaming_text=self._on_streaming_text,
            )
            self._transcriber = transcriber_runtime.transcriber
            self._is_streaming_mode = transcriber_runtime.is_streaming_mode
            self._streaming_transcriber = transcriber_runtime.streaming_transcriber

            # 7. 重建/移除润色器
            self._polish_enabled = polish_cfg.get("enabled", True)
            if self._polish_enabled:
                self._polisher = create_polisher(new_config, polish_cfg)
            else:
                self._polisher = None

            # 8. 更新录音参数
            self._recorder.sample_rate = rec_cfg["sample_rate"]
            self._recorder.channels = rec_cfg["channels"]
            self._recorder.max_duration = rec_cfg["max_duration"]

            # 9. 更新历史记录配置
            self._history_store = HistoryStore.from_config(history_cfg)

            # 10. 更新托盘菜单语言
            if hasattr(self._tray, "set_language"):
                self._tray.set_language(ui_cfg["language"])

            # 11. 更新结果预览胶囊开关
            self._reload_preview_overlay(new_config)

            # 12. 更新悬浮按钮显示、主题、语言和位置
            floating_cfg = get_floating_control_config(new_config)
            self._floating.configure(
                enabled=floating_cfg["enabled"],
                x=floating_cfg["x"],
                y=floating_cfg["y"],
                theme=ui_cfg["theme"],
                language=ui_cfg["language"],
            )

            # 13. 热键变更时重建监听器
            hotkey_cfg = get_hotkey_config(new_config)
            old_hotkey = get_hotkey_config(self._config).get("combination", "")
            new_hotkey = hotkey_cfg.get("combination", "")
            if new_hotkey and new_hotkey != old_hotkey:
                log.info("快捷键已变更: %s → %s，正在重启监听器...", old_hotkey, new_hotkey)
                try:
                    self._hotkey_listener.stop()
                    self._hotkey_listener = HotkeyListener(
                        combination_str=new_hotkey,
                        on_activate=self._on_hotkey_press,
                        on_deactivate=self._on_hotkey_release,
                        on_cancel=self._on_cancel,
                    )
                    # 在新线程中启动（start() 会阻塞）
                    hotkey_thread = threading.Thread(
                        target=self._hotkey_listener.start,
                        daemon=True,
                    )
                    hotkey_thread.start()
                    log.info("新快捷键 %s 已生效", new_hotkey)
                except Exception as e:
                    log.error("重启热键监听器失败: %s", e)

            # 13. 更新内部配置引用
            self._config = new_config

            log.info("配置已热重载完成")
            return (True, "配置已保存并立即生效")

        except ValueError as e:
            log.error("配置验证失败: %s", e)
            return (False, str(e))
        except Exception as e:
            log.error("热重载配置失败: %s", e)
            return (False, f"保存失败: {e}")
