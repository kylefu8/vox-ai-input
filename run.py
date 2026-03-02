"""
AI-Input 程序入口

启动 AI 语音输入法：长按快捷键说话，松开后自动转写、润色并粘贴到当前应用。
支持 --test 参数进入测试模式（按回车控制录音，便于调试）。
"""

import sys

from src.logger import setup_logger

log = setup_logger("main")


def run_test_mode():
    """
    测试模式：按回车控制录音，方便在终端中调试。

    完整流水线：按回车录音 → 按回车停止 → 转写 → 润色 → 粘贴。
    """
    from src.config import (
        load_config, get_azure_config, get_recording_config, get_polish_config
    )
    from src.output import paste_text
    from src.polisher import Polisher
    from src.recorder import Recorder
    from src.transcriber import Transcriber

    log.info("=" * 50)
    log.info("AI-Input 语音输入法 — 测试模式")
    log.info("=" * 50)

    # 加载配置
    config = load_config()
    azure_cfg = get_azure_config(config)
    rec_cfg = get_recording_config(config)
    polish_cfg = get_polish_config(config)

    # 初始化模块
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
            transcriber.cleanup_audio(wav_path)

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


def run_app():
    """
    正常模式：启动 AIInputApp，长按快捷键说话。
    """
    from src.app import AIInputApp

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
        python run.py          # 正常模式（长按快捷键说话）
        python run.py --test   # 测试模式（按回车控制录音）
    """
    if "--test" in sys.argv:
        run_test_mode()
    else:
        run_app()


if __name__ == "__main__":
    main()
