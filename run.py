"""
Vox AI Input 程序入口

启动 AI 语音输入法：长按快捷键说话，松开后自动转写、润色并粘贴到当前应用。
支持 --test 参数进入测试模式（按回车控制录音，便于调试）。
"""

import sys

from src.logger import setup_logger

log = setup_logger("main")

__version__ = "0.0.2"


def _create_components():
    """
    创建核心组件（录音器、转写器、润色器）。

    从 config.yaml 加载配置，初始化各模块。
    供 run_test_mode() 和 AIInputApp 复用同一套初始化逻辑。

    Returns:
        tuple: (recorder, transcriber, polisher_or_none, polish_config)
    """
    from src.config import (
        load_config, get_azure_config, get_recording_config, get_polish_config
    )
    from src.polisher import Polisher
    from src.recorder import Recorder
    from src.transcriber import Transcriber

    config = load_config()
    azure_cfg = get_azure_config(config)
    rec_cfg = get_recording_config(config)
    polish_cfg = get_polish_config(config)

    recorder = Recorder(
        sample_rate=rec_cfg["sample_rate"],
        channels=rec_cfg["channels"],
        max_duration=rec_cfg["max_duration"],
    )

    transcriber = Transcriber(
        endpoint=azure_cfg["endpoint"],
        api_key=azure_cfg["api_key"],
        api_version=azure_cfg["api_version"],
        deployment=azure_cfg["whisper_deployment"],
    )

    polisher = None
    if polish_cfg.get("enabled", True):
        polisher = Polisher(
            endpoint=azure_cfg["endpoint"],
            api_key=azure_cfg["api_key"],
            api_version=azure_cfg["api_version"],
            deployment=azure_cfg["gpt_deployment"],
        )

    return recorder, transcriber, polisher, polish_cfg


def run_test_mode():
    """
    测试模式：按回车控制录音，方便在终端中调试。

    完整流水线：按回车录音 → 按回车停止 → 转写 → 润色 → 粘贴。
    """
    from src.output import paste_text
    from src.transcriber import cleanup_audio

    log.info("=" * 50)
    log.info("Vox AI Input 语音输入法 — 测试模式")
    log.info("=" * 50)

    recorder, transcriber, polisher, polish_cfg = _create_components()

    log.info("")
    log.info("使用方法: 按 [回车] 开始录音，再按 [回车] 停止录音")
    log.info("说完话后，文字会自动粘贴到当前应用中")
    log.info("按 Ctrl+C 退出程序")
    log.info("")

    try:
        while True:
            input(">>> 按 [回车] 开始录音...")

            if not recorder.start():
                log.error("录音启动失败，请检查麦克风")
                continue

            input(">>> 录音中... 按 [回车] 停止录音")

            wav_path = recorder.stop()
            if not wav_path:
                log.warning("没有有效的录音数据，请重试")
                continue

            raw_text = transcriber.transcribe(
                wav_path,
                language=polish_cfg.get("language", "zh"),
            )
            cleanup_audio(wav_path)

            if not raw_text:
                log.warning("未能转写出文字，请检查是否有语音输入")
                continue

            if polisher:
                final_text = polisher.polish(raw_text)
            else:
                final_text = raw_text
                log.info("润色已关闭，直接使用原始转写文字")

            if not final_text:
                log.warning("润色后文字为空，跳过")
                continue

            log.info("")
            log.info("🎯 最终文字:")
            log.info("-" * 40)
            print(f"\n{final_text}\n")
            log.info("-" * 40)

            paste_text(final_text)
            log.info("")

    except KeyboardInterrupt:
        log.info("")
        log.info("程序已退出，再见！")
        sys.exit(0)


def _hide_console_window():
    """
    在 Windows 上隐藏控制台窗口。

    使用 Windows API 将控制台窗口隐藏，让程序只以系统托盘图标形式运行。
    在非 Windows 系统或没有控制台窗口时静默跳过。
    """
    import platform

    if platform.system() != "Windows":
        return

    try:
        import ctypes
        # 获取当前控制台窗口句柄
        console_window = ctypes.windll.kernel32.GetConsoleWindow()
        if console_window:
            # SW_HIDE = 0，隐藏窗口
            ctypes.windll.user32.ShowWindow(console_window, 0)
            log.debug("控制台窗口已隐藏")
    except Exception as e:
        log.debug("隐藏控制台窗口失败（不影响运行）: %s", e)


def run_app(hide_console=True):
    """
    正常模式：启动 AIInputApp，长按快捷键说话。

    在 Windows 上默认隐藏控制台窗口，程序通过系统托盘图标运行。

    Args:
        hide_console: 是否隐藏控制台窗口，默认 True
    """
    from src.app import AIInputApp

    # 隐藏控制台窗口（Windows），程序只通过托盘图标交互
    if hide_console:
        _hide_console_window()

    try:
        app = AIInputApp()
        app.run()
    except KeyboardInterrupt:
        log.info("")
        log.info("程序已退出，再见！")
        sys.exit(0)


def main():
    """
    程序入口。

    用法:
        python run.py             # 正常模式（隐藏控制台，托盘运行）
        python run.py --test      # 测试模式（按回车控制录音）
        python run.py --visible   # 正常模式但保留控制台窗口（调试用）
        python run.py --setup     # 打开配置向导 Web UI
        python run.py --version   # 显示版本号
    """
    if "--version" in sys.argv:
        print(f"Vox AI Input v{__version__}")
        sys.exit(0)

    if "--setup" in sys.argv:
        from src.setup_ui import run_setup
        run_setup()
        sys.exit(0)

    # 首次启动检测：若 config.yaml 不存在，自动开启配置向导而非直接退出
    from src.paths import get_project_root
    config_path = get_project_root() / "config.yaml"
    if not config_path.exists():
        log.warning("未找到 config.yaml，正在启动配置向导...")
        try:
            from src.setup_ui import run_setup
            run_setup()
        except Exception as e:
            log.error("配置向导启动失败: %s", e)
        # 配置向导结束后重新检查
        if not config_path.exists():
            log.error("配置文件仍未创建，无法启动。")
            log.error("请复制 config.example.yaml 为 config.yaml 并填入 Azure API 信息")
            sys.exit(1)
        log.info("配置文件已创建，继续启动...")

    if "--test" in sys.argv:
        run_test_mode()
    elif "--visible" in sys.argv:
        run_app(hide_console=False)
    else:
        run_app()


if __name__ == "__main__":
    main()
