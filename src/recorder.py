"""
麦克风录音模块

使用 sounddevice 的回调模式进行实时录音，不阻塞主线程。
录音数据暂存在内存中，停止后保存为临时 WAV 文件供后续 API 调用使用。
"""

import platform
import tempfile
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

from src.logger import setup_logger

log = setup_logger(__name__)


def _find_usable_input_device():
    """
    查找一个可用的音频输入设备。

    在 Windows 上，优先使用 WASAPI/MME/DirectSound（高层 API）的设备，
    因为 WDM-KS（低层内核驱动）虽然能枚举硬件但常常无法打开流。

    Returns:
        tuple[int, dict] | None: (设备索引, 设备信息字典)，找不到返回 None
    """
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception as e:
        log.debug("查询音频设备失败: %s", e)
        return None

    # 按 hostapi 优先级排序输入设备：WASAPI > DirectSound > MME > WDM-KS
    # WDM-KS 设备在 RDP 等场景下虽能枚举但无法打开
    HIGH_LEVEL_APIS = {"Windows WASAPI", "Windows DirectSound", "MME"}

    high_level_inputs = []  # 高层 API 设备（可靠）
    low_level_inputs = []   # WDM-KS 等低层设备（不一定可用）

    for i, d in enumerate(devices):
        if d.get("max_input_channels", 0) <= 0:
            continue
        api_name = hostapis[d["hostapi"]]["name"] if d["hostapi"] < len(hostapis) else ""
        if api_name in HIGH_LEVEL_APIS:
            high_level_inputs.append((i, d))
        else:
            low_level_inputs.append((i, d))

    # 从可靠列表中挑选：优先麦克风、排除虚拟设备
    for candidates in (high_level_inputs, low_level_inputs):
        best = _pick_best_mic(candidates)
        if best is not None:
            return best

    return None


def _pick_best_mic(candidates):
    """
    从候选设备列表中挑选最佳麦克风。

    优先级：名字含"麦克风/mic/microphone" > 非虚拟设备 > 第一个设备

    Args:
        candidates: list of (index, device_dict)

    Returns:
        tuple[int, dict] | None
    """
    if not candidates:
        return None

    best = None
    for idx, d in candidates:
        name_lower = d["name"].lower()
        # 跳过虚拟/混音设备
        if any(kw in name_lower for kw in ("stereo mix", "立体声混音", "loopback")):
            continue
        # 优先麦克风
        if any(kw in name_lower for kw in ("麦克风", "mic", "microphone")):
            return (idx, d)
        if best is None:
            best = (idx, d)

    return best if best is not None else (candidates[0] if candidates else None)


def check_audio_input():
    """
    检查系统是否有可用的音频输入设备（麦克风）。

    启动时调用一次：
    - 没有任何输入设备 → 提示并退出
    - 有默认设备 → 打印设备名继续
    - 无默认设备但有高层 API 设备 → 自动选择并设为默认
    - 只有 WDM-KS 设备（典型 RDP 场景）→ 提示用户开启麦克风重定向

    Raises:
        SystemExit: 当没有可用的音频输入设备时
    """
    try:
        devices = sd.query_devices()
    except Exception as e:
        log.error("无法查询音频设备: %s", e)
        log.error("请检查系统音频驱动是否正常安装")
        raise SystemExit(1)

    input_devices = [
        (i, d) for i, d in enumerate(devices)
        if d.get("max_input_channels", 0) > 0
    ]

    if not input_devices:
        log.error("未检测到任何音频输入设备（麦克风）")
        log.error("请连接麦克风后重新启动程序")
        raise SystemExit(1)

    # 检查是否有默认输入设备
    try:
        default_idx = sd.default.device[0]
        if default_idx >= 0:
            default_dev = devices[default_idx]
            if default_dev.get("max_input_channels", 0) > 0:
                log.info("检测到默认麦克风: [%d] %s", default_idx, default_dev["name"])
                return
    except Exception:
        pass

    # 无默认设备 → 尝试自动选择
    chosen = _find_usable_input_device()

    if chosen is None:
        # 所有设备都在 WDM-KS 上？很可能是 RDP 场景
        _print_rdp_hint(input_devices)
        raise SystemExit(1)

    chosen_idx, chosen_dev = chosen

    # 检查设备所在的 hostapi 是否为 WDM-KS（不可靠）
    try:
        hostapis = sd.query_hostapis()
        api_name = hostapis[chosen_dev["hostapi"]]["name"]
        if "WDM-KS" in api_name:
            # WDM-KS 设备不可靠，很可能是 RDP
            _print_rdp_hint(input_devices)
            raise SystemExit(1)
    except (IndexError, KeyError):
        pass

    sd.default.device = (chosen_idx, sd.default.device[1])
    log.info(
        "未检测到默认麦克风，已自动选择: [%d] %s",
        chosen_idx, chosen_dev["name"],
    )


def _print_rdp_hint(input_devices):
    """打印 RDP 麦克风重定向提示信息。"""
    log.error("=" * 55)
    log.error("未找到可用的麦克风！")
    log.error("")
    log.error("检测到你可能正在使用远程桌面 (RDP) 连接。")
    log.error("RDP 默认不转发本地麦克风，需要手动开启：")
    log.error("")
    log.error("  1. 打开「远程桌面连接」(mstsc)")
    log.error("  2. 点击「显示选项」→「本地资源」选项卡")
    log.error("  3. 远程音频 → 点击「设置」")
    log.error("  4. 远程音频录制 → 选择「从此计算机录制」")
    log.error("  5. 确定后重新连接")
    log.error("")
    log.error("如果你在电脑前（非 RDP），请检查：")
    log.error("  - Windows 声音设置中麦克风是否被禁用")
    log.error("  - 设备管理器中音频驱动是否正常")
    log.error("=" * 55)
    if input_devices:
        log.debug("系统枚举到以下输入设备（均不可用）：")
        for idx, d in input_devices:
            try:
                hostapis = sd.query_hostapis()
                api = hostapis[d["hostapi"]]["name"]
            except Exception:
                api = "?"
            log.debug("  [%d] %s (%s)", idx, d["name"], api)


class Recorder:
    """
    麦克风录音器。

    使用 sounddevice 的回调（callback）模式录音：
    - start() 开始录音，音频数据通过回调函数持续写入内存缓冲区
    - stop() 停止录音，将缓冲区数据保存为 WAV 文件并返回文件路径

    这种回调模式不会阻塞调用线程，适合在主线程监听热键的同时录音。
    """

    def __init__(self, sample_rate=16000, channels=1, max_duration=60):
        """
        初始化录音器。

        Args:
            sample_rate: 采样率，默认 16000 Hz（Whisper 推荐值）
            channels: 声道数，默认 1（单声道）
            max_duration: 最大录音时长（秒），超过自动停止
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_duration = max_duration

        # 录音状态
        self._is_recording = False
        self._stream = None
        self._audio_chunks = []  # 存放录音数据片段
        self._lock = threading.Lock()       # 保护 _audio_chunks
        self._state_lock = threading.Lock() # 保护 start/stop 并发

        # 自动停止定时器
        self._auto_stop_timer = None
        # 倒计时提醒定时器
        self._countdown_timer = None
        # 当录音自动停止时的回调函数
        self._on_auto_stop = None
        # 倒计时开始时的回调函数
        self._on_countdown = None

    @property
    def is_recording(self):
        """当前是否正在录音。"""
        return self._is_recording

    def start(self, on_auto_stop=None, on_countdown=None):
        """
        开始录音。

        Args:
            on_auto_stop: 可选回调函数，当录音达到最大时长自动停止时调用
            on_countdown: 可选回调函数(seconds)，倒计时开始时调用

        Returns:
            bool: 是否成功开始录音
        """
        with self._state_lock:
            if self._is_recording:
                log.warning("已经在录音中，忽略重复的 start 调用")
                return False

            try:
                # 清空之前的录音数据
                self._audio_chunks = []
                self._on_auto_stop = on_auto_stop
                self._on_countdown = on_countdown

                # 创建音频输入流（回调模式）
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=self.channels,
                    dtype="float32",
                    callback=self._audio_callback,
                )
                self._stream.start()
                self._is_recording = True

                # 设置最大录音时长的自动停止定时器
                self._auto_stop_timer = threading.Timer(
                    self.max_duration, self._auto_stop
                )
                self._auto_stop_timer.daemon = True
                self._auto_stop_timer.start()

                # 设置倒计时提醒定时器（最后 5 秒触发）
                countdown_secs = 5
                countdown_delay = self.max_duration - countdown_secs
                if countdown_delay > 0 and self._on_countdown:
                    self._countdown_timer = threading.Timer(
                        countdown_delay,
                        lambda: self._on_countdown(countdown_secs),
                    )
                    self._countdown_timer.daemon = True
                    self._countdown_timer.start()

                log.info("🎤 开始录音（采样率: %d Hz，最长: %d 秒）",
                          self.sample_rate, self.max_duration)
                return True

            except sd.PortAudioError as e:
                log.error("无法访问麦克风: %s", e)
                log.error("请检查系统是否已授权麦克风访问权限")
                # 输出设备诊断信息，帮助用户排查问题
                try:
                    devices = sd.query_devices()
                    log.error("可用音频设备:")
                    for i, d in enumerate(devices):
                        if d["max_input_channels"] > 0:
                            log.error("  [%d] %s", i, d["name"])
                except Exception:
                    pass
                self._is_recording = False
                return False
            except Exception as e:
                log.error("录音启动失败: %s", e)
                self._is_recording = False
                return False

    def stop(self):
        """
        停止录音并保存为 WAV 文件。

        线程安全：可从多个线程调用（手动停止 / 自动停止），
        通过 _state_lock 保证只有第一个调用者执行实际停止。

        Returns:
            Path | None: 录音文件路径，如果录音失败或无数据则返回 None
        """
        with self._state_lock:
            if not self._is_recording:
                log.warning("当前未在录音，忽略 stop 调用")
                return None

            # 标记为非录音状态（在锁内，防止重入）
            self._is_recording = False

            # 取消自动停止定时器
            if self._auto_stop_timer:
                self._auto_stop_timer.cancel()
                self._auto_stop_timer = None

            # 取消倒计时定时器
            if self._countdown_timer:
                self._countdown_timer.cancel()
                self._countdown_timer = None

            # 停止并关闭音频流
            try:
                if self._stream:
                    self._stream.stop()
                    self._stream.close()
            except Exception as e:
                log.warning("关闭音频流时出错: %s", e)
            finally:
                self._stream = None

        log.info("⏹️  停止录音")

        # 把所有录音片段拼接成一个完整的 numpy 数组
        with self._lock:
            if not self._audio_chunks:
                log.warning("录音数据为空，可能麦克风未正常工作")
                return None
            audio_data = np.concatenate(self._audio_chunks, axis=0)

        duration = len(audio_data) / self.sample_rate
        log.debug("录音时长: %.1f 秒（%d 个采样点）", duration, len(audio_data))

        # 如果录音太短（不到 0.3 秒），可能是误触
        if duration < 0.3:
            log.warning("录音时长不足 0.3 秒，跳过处理")
            return None

        # 保存为临时 WAV 文件
        try:
            wav_path = self._save_to_wav(audio_data)
            log.debug("录音已保存: %s", wav_path)
            return wav_path
        except Exception as e:
            log.error("保存录音文件失败: %s", e)
            return None

    def _audio_callback(self, indata, frames, time_info, status):
        """
        sounddevice 的回调函数，每收到一段音频数据就调用一次。

        这个函数在音频线程中执行，不能做耗时操作。

        Args:
            indata: 输入音频数据（numpy 数组）
            frames: 帧数
            time_info: 时间信息
            status: 状态标志（溢出等）
        """
        if status:
            log.warning("音频流状态异常: %s", status)

        # 复制一份数据存入缓冲区（indata 的内存会被复用）
        with self._lock:
            self._audio_chunks.append(indata.copy())

    def _save_to_wav(self, audio_data):
        """
        将 numpy 音频数据保存为临时 WAV 文件。

        Args:
            audio_data: numpy 数组，形状为 (samples,) 或 (samples, channels)

        Returns:
            Path: 保存的 WAV 文件路径
        """
        # 在系统临时目录创建 WAV 文件
        temp_file = tempfile.NamedTemporaryFile(
            suffix=".wav", prefix="vox_ai_input_", delete=False
        )
        wav_path = Path(temp_file.name)
        temp_file.close()

        sf.write(str(wav_path), audio_data, self.sample_rate)
        return wav_path

    def _auto_stop(self):
        """
        当录音达到最大时长时自动停止。
        在 Timer 线程中执行。
        """
        log.warning("录音已达最大时长 %d 秒，自动停止", self.max_duration)
        wav_path = self.stop()
        if self._on_auto_stop and wav_path:
            self._on_auto_stop(wav_path)
