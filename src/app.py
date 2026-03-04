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
import time
from typing import Optional

from src.config import (
    load_config,
    save_config,
    get_azure_config,
    get_recording_config,
    get_hotkey_config,
    get_polish_config,
)
from src.hotkey import HotkeyListener
from src.interfaces import TranscriberProtocol, PolisherProtocol
from src.logger import setup_logger
from src.notifier import play_start_sound, play_stop_sound, create_default_sounds
from src.output import paste_text
from src.polisher import Polisher
from src.countdown import CountdownOverlay
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

        # 初始化转写器（满足 TranscriberProtocol）
        self._transcriber: TranscriberProtocol = Transcriber(
            endpoint=azure_cfg["endpoint"],
            api_key=azure_cfg["api_key"],
            api_version=azure_cfg["api_version"],
            deployment=azure_cfg["whisper_deployment"],
        )

        # 初始化润色器（如果启用，满足 PolisherProtocol）
        self._polisher: Optional[PolisherProtocol] = None
        self._polish_enabled = polish_cfg.get("enabled", True)
        if self._polish_enabled:
            self._polisher = Polisher(
                endpoint=azure_cfg["endpoint"],
                api_key=azure_cfg["api_key"],
                api_version=azure_cfg["api_version"],
                deployment=azure_cfg["gpt_deployment"],
                system_prompt=polish_cfg.get("system_prompt", "") or None,
                translate_to=polish_cfg.get("translate_to", ""),
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
        """
        # 如果正在处理上一条语音，跳过（加锁读取，避免竞态）
        with self._processing_lock:
            if self._is_processing:
                log.warning("上一条语音还在处理中，请稍候...")
                return

        # 更新托盘状态为录音中
        self._tray.set_state(STATE_RECORDING)

        # 播放开始提示音
        play_start_sound()

        # 开始录音（设置自动停止回调 + 倒计时回调）
        if not self._recorder.start(
            on_auto_stop=self._on_auto_stop,
            on_countdown=self._on_countdown_start,
        ):
            # 录音启动失败，恢复空闲状态
            log.error("录音启动失败，请检查麦克风")
            self._tray.set_state(STATE_IDLE)

    def _on_hotkey_release(self):
        """
        热键松开回调 — 停止录音并启动后台处理。

        在热键监听线程中调用。
        先停录音再播提示音，避免 sounddevice 设备冲突。
        """
        if not self._recorder.is_recording:
            return

        # 先停止录音（释放 sounddevice 设备）
        wav_path = self._recorder.stop()

        # 关闭倒计时浮窗
        self._countdown.dismiss()

        # 再播放结束提示音（此时设备已释放，避免冲突）
        play_stop_sound()
        if not wav_path:
            log.warning("没有有效的录音数据")
            self._tray.set_state(STATE_IDLE)
            return

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

        与手动松开热键的路径保持一致：播放停止提示音 + 后台线程处理。
        在 Timer 线程中调用，不能直接同步执行 _process_audio（会阻塞 Timer）。
        注意：此时录音已经停止（由 Recorder 内部处理），sounddevice 设备已释放，
        可以安全播放提示音。

        Args:
            wav_path: 录音文件路径
        """
        # 关闭倒计时浮窗
        self._countdown.dismiss()

        # 播放结束提示音（录音已停止，设备已释放）
        play_stop_sound()

        # 启动后台线程处理（和手动路径一致，不阻塞 Timer 线程）
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
        t_start = time.monotonic()

        try:
            # 1. 语音转文字
            t1 = time.monotonic()
            raw_text = self._transcriber.transcribe(
                wav_path, language=self._language
            )

            if not raw_text:
                log.warning("转写结果为空，跳过")
                return

            self._session_api_calls += 1  # 转写计为一次 API 调用
            t2 = time.monotonic()
            log.info("⏱️  转写耗时: %.1f 秒", t2 - t1)

            # 2. AI 润色
            if self._polisher and self._polish_enabled:
                final_text = self._polisher.polish(raw_text)
            else:
                final_text = raw_text

            if not final_text:
                log.warning("润色结果为空，跳过")
                return

            t3 = time.monotonic()
            if self._polisher and self._polish_enabled:
                self._session_api_calls += 1  # 润色计为一次 API 调用
                log.info("⏱️  润色耗时: %.1f 秒", t3 - t2)

            # 3. 翻译已合并进润色 prompt，无需单独步骤

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

        except Exception as e:
            log.error("处理音频时出错: %s", e)

        finally:
            # 无论成功与否，都清理临时音频文件
            cleanup_audio(wav_path)
            with self._processing_lock:
                self._is_processing = False
            # 处理完毕，恢复空闲状态
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

            # 4. 重建转写器
            self._transcriber = Transcriber(
                endpoint=azure_cfg["endpoint"],
                api_key=azure_cfg["api_key"],
                api_version=azure_cfg["api_version"],
                deployment=azure_cfg["whisper_deployment"],
            )

            # 5. 重建/移除润色器
            self._polish_enabled = polish_cfg.get("enabled", True)
            if self._polish_enabled:
                self._polisher = Polisher(
                    endpoint=azure_cfg["endpoint"],
                    api_key=azure_cfg["api_key"],
                    api_version=azure_cfg["api_version"],
                    deployment=azure_cfg["gpt_deployment"],
                    system_prompt=polish_cfg.get("system_prompt", "") or None,
                    translate_to=polish_cfg.get("translate_to", ""),
                )
            else:
                self._polisher = None

            # 6. 更新语言设置
            self._language = polish_cfg.get("language", "zh")

            # 7. 更新录音参数（下次录音时生效）
            self._recorder.sample_rate = rec_cfg["sample_rate"]
            self._recorder.channels = rec_cfg["channels"]
            self._recorder.max_duration = rec_cfg["max_duration"]

            # 8. 热键变更时重建监听器
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

            # 9. 更新内部配置引用
            self._config = new_config

            log.info("配置已热重载完成")
            return (True, "配置已保存并立即生效")

        except ValueError as e:
            log.error("配置验证失败: %s", e)
            return (False, str(e))
        except Exception as e:
            log.error("热重载配置失败: %s", e)
            return (False, f"保存失败: {e}")
