"""
统一日志模块

为整个项目提供统一的日志配置，输出格式包含时间戳、模块名和日志级别，
方便在 macOS 和 Windows 上排查问题。

支持通过环境变量 AI_INPUT_LOG_LEVEL 设置日志级别：
    AI_INPUT_LOG_LEVEL=DEBUG python run.py
"""

import logging
import os
import platform
import sys


def _get_log_level():
    """
    从环境变量获取日志级别，默认 INFO。

    支持: DEBUG, INFO, WARNING, ERROR, CRITICAL

    Returns:
        int: logging 级别常量
    """
    level_str = os.environ.get("AI_INPUT_LOG_LEVEL", "INFO").upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str, logging.INFO)


def setup_logger(name, level=None):
    """
    创建并返回一个配置好的 logger 实例。

    Args:
        name: logger 名称，通常传入模块的 __name__
        level: 日志级别，默认从环境变量 AI_INPUT_LOG_LEVEL 获取

    Returns:
        配置好的 logging.Logger 实例
    """
    if level is None:
        level = _get_log_level()

    logger = logging.getLogger(name)

    # 避免重复添加 handler（模块被多次 import 时）
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # 禁止向父 logger 传播，避免在 pytest 等环境中日志双重输出
    logger.propagate = False

    # 控制台输出 handler
    # Windows 旧版终端（cmd.exe / PowerShell 5）默认编码为 GBK，
    # 遇到 Emoji 会抛出 UnicodeEncodeError。这里显式设置 UTF-8 + errors="replace"
    # 保证日志不会因为编码问题导致程序崩溃。
    if platform.system() == "Windows":
        try:
            stream = open(sys.stdout.fileno(), mode="w",
                          encoding="utf-8", errors="replace",
                          closefd=False)
        except Exception:
            stream = sys.stdout
    else:
        stream = sys.stdout

    console_handler = logging.StreamHandler(stream)
    console_handler.setLevel(level)

    # 日志格式：时间 | 级别 | 模块名 | 消息
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-12s | %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger
