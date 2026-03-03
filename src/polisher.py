"""
文字润色模块

调用 Azure OpenAI 的 GPT-4o-mini，对语音转写的文字进行最小化润色：
补标点、纠错别字、去口语填充词，但不改变原意。
实现了 PolisherProtocol 接口，可被其他润色实现替换。
"""

from openai import APITimeoutError, APIConnectionError

from src.azure_client import get_azure_client
from src.logger import setup_logger

log = setup_logger(__name__)

# 润色的系统提示词
POLISH_SYSTEM_PROMPT = """你是一个语音输入后处理助手。对语音转写的文字进行最小化润色：
1. 保留原意，不增删实质内容
2. 补充标点符号
3. 纠正语音识别导致的错别字（同音字等）
4. 去除口语填充词（嗯、那个、就是说）
5. 保留中英文混合：英文单词、品牌名、技术术语保持英文原样
6. 口述的符号名称转为实际符号，例如：
   - "at" 或 "艾特" → @
   - "井号" → #
   - "斜杠" → /
   - "点" 在邮箱或网址语境中 → .
   - "下划线" → _
   - "百分号" → %
7. 不要过度正式化，不添加额外信息
8. 原文已经很好则原样返回
只输出润色后的纯文本。"""


class Polisher:
    """
    Azure GPT 文字润色处理器。

    实现 PolisherProtocol 接口。
    使用 Azure OpenAI 的 GPT-4o-mini 对语音转写文字进行润色。
    """

    def __init__(self, endpoint, api_key, api_version, deployment):
        """
        初始化润色器。

        Args:
            endpoint: Azure OpenAI 服务端点 URL
            api_key: Azure OpenAI API Key
            api_version: API 版本号
            deployment: GPT 模型的部署名称
        """
        self.deployment = deployment

        # 获取共享的 Azure OpenAI 客户端（超时 30 秒，文字润色响应较快）
        self.client = get_azure_client(
            endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            timeout=30.0,
            max_retries=2,
        )

        log.info("GPT 润色器初始化完成（部署: %s）", deployment)

    def polish(self, raw_text):
        """
        对语音转写的原始文字进行润色。

        Args:
            raw_text: Whisper 转写的原始文字

        Returns:
            str | None: 润色后的文字。如果调用失败返回 None。
        """
        if not raw_text or not raw_text.strip():
            log.warning("输入文字为空，跳过润色")
            return None

        log.info("🤖 正在调用 GPT 润色文字...")

        try:
            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": POLISH_SYSTEM_PROMPT},
                    {"role": "user", "content": raw_text},
                ],
                temperature=0.3,  # 低温度，减少创造性改写
                max_tokens=2000,
            )

            polished = response.choices[0].message.content.strip()

            if not polished:
                log.warning("GPT 返回了空内容，使用原始文字")
                return raw_text

            # 如果润色结果和原文差异不大，记录一下
            if polished == raw_text:
                log.info("✅ 原文已经很好，无需修改")
            else:
                log.info("✅ 润色完成")
                log.debug("   原文: %s", raw_text[:60] + "..." if len(raw_text) > 60 else raw_text)
                log.debug("   润色: %s", polished[:60] + "..." if len(polished) > 60 else polished)

            return polished

        except APITimeoutError:
            log.error("GPT API 调用超时（30秒），返回原始文字")
            return raw_text
        except APIConnectionError as e:
            log.error("无法连接到 Azure 服务: %s，返回原始文字", e)
            return raw_text
        except Exception as e:
            log.error("GPT API 调用失败: %s", e)
            log.error("将返回原始转写文字（未润色）")
            return raw_text  # 降级策略：润色失败时返回原文
