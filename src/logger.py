"""
统一日志模块

为整个项目提供统一的日志配置，输出格式包含时间戳、模块名和日志级别，
方便在 macOS 和 Windows 上排查问题。
"""

import logging
import sys


def setup_logger(name, level=logging.INFO):
    """
    创建并返回一个配置好的 logger 实例。

    Args:
        name: logger 名称，通常传入模块的 __name__
        level: 日志级别，默认 INFO

    Returns:
        配置好的 logging.Logger 实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler（模块被多次 import 时）
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # 控制台输出 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # 日志格式：时间 | 级别 | 模块名 | 消息
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-12s | %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)

    return logger
