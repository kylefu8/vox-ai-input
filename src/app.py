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
    get_azure_config,
    get_recording_config,
    get_hotkey_config,
    get_polish_config,
    get_stt_config,
)
from src.hotkey import HotkeyListener
from src.interfaces import TranscriberProtocol, PolisherProtocol
from src.logger import setup_logger
from src.notifier import play_start_sound, play_stop_sound, create_default_sounds
from src.output import paste_text
from src.polisher import Polisher
from src.countdown import CountdownOverlay
from src.preview_overlay import PreviewOverlay
from src.log_window import LogWindow
from src.recorder import Recorder, check_audio_input
from src.updater import Updater
from src.settings_window import open_settings
from src.transcriber import Transcriber, cleanup_audio
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
        log.info("Vox AI Input 语音输入法 — 正在启动...")
        log.info("=" * 50)

        # 检查是否首次启动（API 未配置）
        import builtins
        self._need_setup = getattr(builtins, "_VOX_NEED_SETUP", False)

        # 加载配置
        self._config = load_config()
        azure_cfg = get_azure_config(self._config)
        rec_cfg = get_recording_config(self._config)
        hotkey_cfg = get_hotkey_config(self._config)
        polish_cfg = get_polish_config(self._config)

        # 检查麦克风是否可用（不可用则提示并退出）
        check_audio_input()

        # 初始化录音器
        self._recorder = Recorder(
            sample_rate=rec_cfg["sample_rate"],
            channels=rec_cfg["channels"],
            max_duration=rec_cfg["max_duration"],
        )

        # 初始化转写器和润色器（首次启动时跳过，等用户填写 API 后通过设置窗口重建）
        self._transcriber: Optional[TranscriberProtocol] = None
        self._polisher: Optional[PolisherProtocol] = None
        self._polish_enabled = polish_cfg.get("enabled", True)

        # 流式模式标志 + 流式转写器引用
        self._is_streaming_mode = False
        self._streaming_transcriber = None

        if not self._need_setup:
            try:
                stt_cfg = get_stt_config(self._config)
                self._transcriber = self._create_transcriber(stt_cfg, azure_cfg)
                if self._polish_enabled:
                    self._polisher = Polisher(
                        endpoint=azure_cfg["endpoint"],
                        api_key=azure_cfg["api_key"],
                        api_version=azure_cfg["api_version"],
                        deployment=azure_cfg["gpt_deployment"],
                        system_prompt=polish_cfg.get("system_prompt", "") or None,
                        translate_to=polish_cfg.get("translate_to", ""),
                        show_original=polish_cfg.get("show_original", False),
                    )
            except Exception as e:
                log.warning("初始化转写/润色模块失败（请通过设置窗口配置）: %s", e)
                self._need_setup = True
        else:
            log.info("首次启动，跳过 API 初始化，等待用户配置")

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

        # 程序退出事件（主线程用此等待）
        self._shutdown_event = threading.Event()

        # 生成默认提示音文件
        create_default_sounds()

        # 最近一次处理的结果（供设置窗口显示）
        self._last_result_text = ""
        self._last_result_duration = 0.0

        # 会话用量统计（让用户了解 API 调用次数）
        self._session_api_calls = 0

        # 录音倒计时浮窗
        self._countdown = CountdownOverlay()

        # 预览浮窗（实时显示转写/润色状态和结果）
        self._preview = PreviewOverlay()

        # 实时日志窗口
        self._log_window = LogWindow()

        # 版本更新管理器
        self._updater = Updater()

        # 初始化系统托盘图标（带设置/日志/更新回调）
        self._tray = TrayIcon(
            on_quit=self._shutdown,
            on_settings=self._open_settings,
            on_log=self._open_log,
            on_update=self._check_update,
        )

        log.info("所有模块初始化完成！")

    def _create_transcriber(self, stt_cfg, azure_cfg):
        """
        工厂方法：根据 STT 后端配置创建对应的转写器。

        - backend == "local" + streaming model + streaming=True → 创建 StreamingTranscriber
        - backend == "local" → 创建 LocalTranscriber（本地离线推理）
        - backend == "azure" → 创建 Transcriber（Azure 云端 API）

        Args:
            stt_cfg: STT 后端配置（来自 get_stt_config）
            azure_cfg: Azure 配置（来自 get_azure_config）

        Returns:
            TranscriberProtocol 实例

        Raises:
            RuntimeError: 模型未下载、sherpa-onnx 未安装等情况
        """
        backend = stt_cfg.get("backend", "azure")

        if backend == "local":
            from src.model_manager import is_model_ready, get_model_dir, MODEL_REGISTRY

            model_type = stt_cfg.get("model_type", "sense_voice")
            num_threads = stt_cfg.get("num_threads", 4)

            if not is_model_ready(model_type):
                raise RuntimeError(
                    f"本地模型 {model_type} 尚未下载。"
                    "请在设置中下载模型后再使用本地转写。"
                )

            model_dir = get_model_dir(model_type)
            language = self._language if hasattr(self, '_language') else "zh"

            # 检查是否为流式模型 + 用户启用了流式转写
            model_info = MODEL_REGISTRY.get(model_type, {})
            is_streaming_model = model_info.get("streaming", False)
            streaming_enabled = stt_cfg.get("streaming", False)

            if is_streaming_model and streaming_enabled:
                # 流式模式：创建 StreamingTranscriber
                from src.streaming_transcriber import StreamingTranscriber

                self._is_streaming_mode = True
                transcriber = StreamingTranscriber(
                    model_dir=model_dir,
                    num_threads=num_threads,
                    on_partial_result=self._on_streaming_text,
                )
                self._streaming_transcriber = transcriber
                log.info("已创建流式转写器（模型: %s，流式模式）", model_type)
                return transcriber
            else:
                # 非流式本地模式
                self._is_streaming_mode = False
                self._streaming_transcriber = None

                if is_streaming_model:
                    # 用 Paraformer 流式模型但走非流式路径
                    from src.streaming_transcriber import StreamingTranscriber
                    transcriber = StreamingTranscriber(
                        model_dir=model_dir,
                        num_threads=num_threads,
                    )
                    log.info("已创建 Paraformer 转写器（非流式模式，模型: %s）", model_type)
                    return transcriber
                else:
                    from src.local_transcriber import LocalTranscriber
                    transcriber = LocalTranscriber(
                        model_dir=model_dir,
                        model_type=model_type,
                        num_threads=num_threads,
                        language=language,
                    )
                    log.info("已创建本地转写器（模型: %s）", model_type)
                    return transcriber

        else:
            # 默认 Azure 模式
            self._is_streaming_mode = False
            self._streaming_transcriber = None
            transcriber = Transcriber(
                endpoint=azure_cfg["endpoint"],
                api_key=azure_cfg["api_key"],
                api_version=azure_cfg["api_version"],
                deployment=azure_cfg["whisper_deployment"],
            )
            log.info("已创建 Azure 云端转写器")
            return transcriber

    def run(self):
        """
        启动应用。

        热键监听在后台线程运行，主线程通过 Event 等待退出信号。
        按 Ctrl+C 或托盘菜单退出。
        """
        # 启动系统托盘图标（后台线程）
        self._tray.start()

        log.info("")
        log.info("🎤 Vox AI Input 已启动！")
        log.info("长按快捷键说话，松开后文字自动粘贴到当前应用")
        log.info("录音中按 Esc 可取消当前录音")
        log.info("按 Ctrl+C 或通过托盘菜单退出程序")
        log.info("")

        # 首次启动（API key 未配置）→ 自动打开设置窗口
        import builtins
        if getattr(builtins, "_VOX_NEED_SETUP", False):
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
        self._tray.stop()
        self._shutdown_event.set()  # 通知主线程退出
        log.info("再见！")

    def _on_hotkey_press(self):
        """
        热键按下回调 — 开始录音。

        在热键监听线程中调用。
        流式模式下同时启动转写会话和预览浮窗。
        """
        # 如果正在处理上一条语音，跳过（加锁读取，避免竞态）
        with self._processing_lock:
            if self._is_processing:
                log.warning("上一条语音还在处理中，请稍候...")
                return

        # 检查转写器是否就绪（首次启动未配置 / 初始化失败时为 None）
        if not self._transcriber:
            log.warning("转写器未就绪，请先在设置中配置转写引擎")
            return

        # 更新托盘状态为录音中
        self._tray.set_state(STATE_RECORDING)

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
        ):
            # 录音启动失败，恢复空闲状态
            log.error("录音启动失败，请检查麦克风")
            self._tray.set_state(STATE_IDLE)
            self._preview.dismiss()

    def _on_hotkey_release(self):
        """
        热键松开回调 — 停止录音并启动后台处理。

        在热键监听线程中调用。
        流式模式：停止转写会话 → 取最终结果 → 润色 → 粘贴
        非流式模式：停录音 → 显示浮窗 → 转写 → 润色 → 粘贴
        """
        if not self._recorder.is_recording:
            return

        # 先停止录音（释放 sounddevice 设备）
        wav_path = self._recorder.stop()

        # 关闭倒计时浮窗
        self._countdown.dismiss()

        # 再播放结束提示音（此时设备已释放，避免冲突）
        play_stop_sound()

        if self._is_streaming_mode and self._streaming_transcriber:
            # ===== 流式模式 =====
            # 停止流式转写会话，获取最终结果
            final_streaming_text = self._streaming_transcriber.stop_session()

            if not final_streaming_text:
                log.warning("流式转写结果为空，跳过")
                self._preview.dismiss()
                self._tray.set_state(STATE_IDLE)
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
                self._tray.set_state(STATE_IDLE)
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
        # 关闭倒计时浮窗
        self._countdown.dismiss()

        # 播放结束提示音（录音已停止，设备已释放）
        play_stop_sound()

        if self._is_streaming_mode and self._streaming_transcriber:
            # ===== 流式模式 =====
            final_streaming_text = self._streaming_transcriber.stop_session()

            if not final_streaming_text:
                log.warning("流式转写结果为空，跳过")
                self._preview.dismiss()
                self._tray.set_state(STATE_IDLE)
                if wav_path:
                    cleanup_audio(wav_path)
                return

            thread = threading.Thread(
                target=self._process_streaming_result,
                args=(final_streaming_text, wav_path),
                daemon=True,
            )
            thread.start()

        else:
            # ===== 非流式模式 =====
            # 显示预览浮窗 — 转写中状态
            self._preview.show(text="", status="📡 转写中...")

            # 启动后台线程处理
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
        self._tray.set_state(STATE_IDLE)
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

        # 更新托盘状态为处理中
        self._tray.set_state(STATE_PROCESSING)
        t_start = time.monotonic()

        try:
            if not self._transcriber:
                log.error("转写器未配置，请先在设置中配置转写引擎")
                self._preview.dismiss()
                return
            # 1. 语音转文字
            t1 = time.monotonic()
            raw_text = self._transcriber.transcribe(
                wav_path, language=self._language
            )

            if not raw_text:
                log.warning("转写结果为空，跳过")
                self._preview.dismiss()
                return

            # 本地模式不计入 API 调用次数
            stt_cfg = get_stt_config(self._config)
            if stt_cfg["backend"] != "local":
                self._session_api_calls += 1
            t2 = time.monotonic()
            log.info("⏱️  转写耗时: %.1f 秒", t2 - t1)

            # 更新浮窗 — 显示原文 + 润色中状态
            if self._polisher and self._polish_enabled:
                self._preview.update_text(raw_text, status="🤖 润色中...")
            else:
                self._preview.update_text(raw_text, status="✅ 完成")

            # 2. AI 润色
            if self._polisher and self._polish_enabled:
                final_text = self._polisher.polish(raw_text)
            else:
                final_text = raw_text

            if not final_text:
                log.warning("润色结果为空，跳过")
                self._preview.dismiss()
                return

            t3 = time.monotonic()
            if self._polisher and self._polish_enabled:
                self._session_api_calls += 1  # 润色计为一次 API 调用
                log.info("⏱️  润色耗时: %.1f 秒", t3 - t2)

            # 3. 更新浮窗显示最终结果
            self._preview.update_text(final_text, status="✅ 完成")
            time.sleep(0.5)  # 短暂展示最终结果

            # 4. 粘贴到当前应用
            log.info("🎯 最终文字: %s",
                      final_text[:80] + "..." if len(final_text) > 80 else final_text)
            paste_text(final_text)

            total_duration = time.monotonic() - t_start
            log.info("⏱️  总处理耗时: %.1f 秒（本次会话已调用 API %d 次）",
                      total_duration, self._session_api_calls)

            # 记录最近结果（供设置窗口显示）
            self._last_result_text = final_text
            self._last_result_duration = total_duration

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
            self._tray.set_state(STATE_IDLE)

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

        # 更新托盘状态为处理中
        self._tray.set_state(STATE_PROCESSING)
        t_start = time.monotonic()

        try:
            log.info("流式转写原文: %s",
                     raw_text[:80] + "..." if len(raw_text) > 80 else raw_text)

            # 更新浮窗 — 显示原文 + 润色中状态
            if self._polisher and self._polish_enabled:
                self._preview.update_text(raw_text, status="🤖 润色中...")
            else:
                self._preview.update_text(raw_text, status="✅ 完成")

            # AI 润色
            if self._polisher and self._polish_enabled:
                t1 = time.monotonic()
                final_text = self._polisher.polish(raw_text)
                t2 = time.monotonic()
                self._session_api_calls += 1
                log.info("⏱️  润色耗时: %.1f 秒", t2 - t1)
            else:
                final_text = raw_text

            if not final_text:
                log.warning("润色结果为空，降级使用原始文字")
                final_text = raw_text

            # 更新浮窗显示最终结果
            self._preview.update_text(final_text, status="✅ 完成")
            time.sleep(0.5)  # 短暂展示最终结果

            # 粘贴到当前应用
            log.info("🎯 最终文字: %s",
                      final_text[:80] + "..." if len(final_text) > 80 else final_text)
            paste_text(final_text)

            total_duration = time.monotonic() - t_start
            log.info("⏱️  总处理耗时: %.1f 秒（本次会话已调用 API %d 次）",
                      total_duration, self._session_api_calls)

            # 记录最近结果
            self._last_result_text = final_text
            self._last_result_duration = total_duration

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
            self._tray.set_state(STATE_IDLE)

    # ==================== 日志窗口 ====================

    def _open_log(self):
        """打开实时日志窗口（从托盘菜单触发）。"""
        self._log_window.show()

    # ==================== 版本更新 ====================

    def _check_update(self):
        """检查更新（从托盘菜单触发），弹出更新对话框。"""
        threading.Thread(target=self._update_flow, daemon=True).start()

    def _update_flow(self):
        """更新流程：检查 → 提示 → 下载 → 替换。在后台线程执行。"""
        import tkinter as tk
        from tkinter import messagebox

        self._updater.check_for_updates(background=False)

        if self._updater.state == "up_to_date":
            # 用临时 Tk 显示消息框
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(
                "检查更新",
                f"已是最新版本 v{self._updater.current_version}",
                parent=root,
            )
            root.destroy()
            return

        if self._updater.state == "error":
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "检查更新失败",
                self._updater.error_message,
                parent=root,
            )
            root.destroy()
            return

        if self._updater.state != "available":
            return

        # 有新版本 → 询问用户
        from src.updater import _is_frozen

        root = tk.Tk()
        root.withdraw()

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

            if messagebox.askyesno("发现新版本", msg, parent=root):
                root.destroy()
                self._do_download_and_apply()
            else:
                root.destroy()
        else:
            # 源码模式 → 引导打开 Release 页面
            msg = (
                f"发现新版本 v{self._updater.latest_version}！\n"
                f"（当前: v{self._updater.current_version}）\n\n"
                "当前以源码模式运行，请手动更新：\n"
                "  git pull\n\n"
                "是否打开 GitHub Release 页面？"
            )
            if messagebox.askyesno("发现新版本", msg, parent=root):
                self._updater.open_release_page()
            root.destroy()

    def _do_download_and_apply(self):
        """下载并应用更新。"""
        import tkinter as tk
        from tkinter import messagebox

        log.info("开始下载更新 v%s ...", self._updater.latest_version)
        self._updater.download_update(background=False)

        if self._updater.state == "error":
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("下载失败", self._updater.error_message, parent=root)
            root.destroy()
            return

        if self._updater.state == "ready":
            root = tk.Tk()
            root.withdraw()
            if messagebox.askyesno(
                "更新就绪",
                "新版本已下载完成！\n\n"
                "点击「是」将退出程序并自动更新。\n"
                "更新完成后程序会自动重新启动。",
                parent=root,
            ):
                root.destroy()
                log.info("用户确认更新，准备替换...")
                if self._updater.apply_update():
                    # 退出当前程序，让 bat 脚本完成替换
                    self._shutdown()
                    import os
                    os._exit(0)
            else:
                root.destroy()

    # ==================== 设置窗口 ====================

    def _open_settings(self):
        """
        打开设置窗口（从托盘菜单触发）。

        在新线程中创建 tkinter 窗口，不阻塞当前线程。
        """
        # 构建状态信息
        state_map = {
            STATE_IDLE: "idle",
            STATE_RECORDING: "recording",
            STATE_PROCESSING: "processing",
        }
        status_info = {
            "state": state_map.get(self._tray._current_state, "idle"),
            "last_text": self._last_result_text,
            "last_duration": self._last_result_duration,
            "session_api_calls": self._session_api_calls,
        }

        open_settings(
            current_config=self._config,
            status_info=status_info,
            on_save=self._reload_config,
        )

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

            # 2. 清除 Azure 客户端缓存（下次调用时自动重建）
            src.azure_client._client_cache.clear()
            log.info("已清除 API 客户端缓存")

            # 3. 提取各部分配置
            azure_cfg = get_azure_config(new_config)
            rec_cfg = get_recording_config(new_config)
            polish_cfg = get_polish_config(new_config)
            stt_cfg = get_stt_config(new_config)

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

            # 5. 更新语言设置（必须在 _create_transcriber 之前，因为工厂方法会读取 self._language）
            self._language = polish_cfg.get("language", "zh")

            # 6. 用工厂方法重建转写器（内部会设置 _is_streaming_mode 和 _streaming_transcriber）
            self._transcriber = self._create_transcriber(stt_cfg, azure_cfg)

            # 7. 重建/移除润色器
            self._polish_enabled = polish_cfg.get("enabled", True)
            if self._polish_enabled:
                self._polisher = Polisher(
                    endpoint=azure_cfg["endpoint"],
                    api_key=azure_cfg["api_key"],
                    api_version=azure_cfg["api_version"],
                    deployment=azure_cfg["gpt_deployment"],
                    system_prompt=polish_cfg.get("system_prompt", "") or None,
                    translate_to=polish_cfg.get("translate_to", ""),
                    show_original=polish_cfg.get("show_original", False),
                )
            else:
                self._polisher = None

            # 8. 更新录音参数（下次录音时生效，语言已在步骤 5 更新）
            self._recorder.sample_rate = rec_cfg["sample_rate"]
            self._recorder.channels = rec_cfg["channels"]
            self._recorder.max_duration = rec_cfg["max_duration"]

            # 9. 热键变更时重建监听器
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

            # 10. 更新内部配置引用
            self._config = new_config

            log.info("配置已热重载完成")
            return (True, "配置已保存并立即生效")

        except ValueError as e:
            log.error("配置验证失败: %s", e)
            return (False, str(e))
        except Exception as e:
            log.error("热重载配置失败: %s", e)
            return (False, f"保存失败: {e}")
