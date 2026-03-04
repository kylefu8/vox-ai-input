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

# 支持的翻译语言映射
TRANSLATE_LANGUAGES = {
    "zh": "简体中文", "zh-TW": "繁体中文", "en": "英语",
    "ja": "日语", "ko": "韩语", "fr": "法语",
    "de": "德语", "es": "西班牙语", "ru": "俄语",
}


def build_prompt(base_prompt="", translate_to=""):
    """
    组合最终的 system prompt。

    Args:
        base_prompt: 基础润色提示词，空=用默认
        translate_to: 翻译目标语言代码，空=不翻译

    Returns:
        str: 完整的 system prompt
    """
    prompt = base_prompt.strip() if base_prompt.strip() else POLISH_SYSTEM_PROMPT

    if translate_to and translate_to in TRANSLATE_LANGUAGES:
        lang_name = TRANSLATE_LANGUAGES[translate_to]
        prompt += f"\n\n最后，将润色后的文字翻译为{lang_name}。只输出翻译结果，不要输出原文。"

    return prompt


class Polisher:
    """
    Azure GPT 文字润色处理器。

    实现 PolisherProtocol 接口。
    使用 Azure OpenAI 的 GPT-4o-mini 对语音转写文字进行润色。
    """

    def __init__(self, endpoint, api_key, api_version, deployment, system_prompt=None, translate_to=""):
        """
        初始化润色器。

        Args:
            endpoint: Azure OpenAI 服务端点 URL
            api_key: Azure OpenAI API Key
            api_version: API 版本号
            deployment: GPT 模型的部署名称
            system_prompt: 自定义基础提示词，留空用默认
            translate_to: 翻译目标语言代码，空=不翻译
        """
        self.deployment = deployment
        self.system_prompt = build_prompt(system_prompt or "", translate_to)

        # 获取共享的 Azure OpenAI 客户端
        # 与 Transcriber 使用相同参数，确保复用同一个客户端和 TCP 连接池
        self.client = get_azure_client(
            endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            timeout=60.0,
            max_retries=0,
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
            # 动态估算 max_tokens：润色输出不会超过输入太多
            # 中文约 1 字 = 1~2 token，留余量但不过度预留
            # 长文本（60 秒录音可能 200+ 字）需要更高上限，否则输出会被截断
            estimated_tokens = min(4096, len(raw_text) * 3 + 100)

            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": raw_text},
                ],
                temperature=0,  # 润色任务不需要创造性，0 最快最确定
                max_tokens=estimated_tokens,
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

    def translate(self, text, target_lang):
        """
        将文字翻译为目标语言。

        使用同一个 GPT 部署，通过 system prompt 指示翻译。

        Args:
            text: 要翻译的文字
            target_lang: 目标语言代码（如 "en", "ja", "zh-TW" 等）

        Returns:
            str | None: 翻译后的文字。失败返回 None。
        """
        if not text or not text.strip():
            return None

        lang_names = {
            "zh": "简体中文", "zh-TW": "繁体中文", "en": "英语",
            "ja": "日语", "ko": "韩语", "fr": "法语",
            "de": "德语", "es": "西班牙语", "ru": "俄语",
        }
        lang_name = lang_names.get(target_lang, target_lang)

        log.info("🌐 正在翻译为%s...", lang_name)

        try:
            estimated_tokens = min(4096, len(text) * 4 + 200)

            response = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"你是一个翻译助手。将用户输入的文字翻译为{lang_name}。\n"
                            "要求：\n"
                            "1. 只输出翻译结果，不要解释\n"
                            "2. 保持原文的语气和风格\n"
                            "3. 专有名词、品牌名可保留原文\n"
                            "4. 如果原文已经是目标语言，原样返回"
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                temperature=0,
                max_tokens=estimated_tokens,
            )

            translated = response.choices[0].message.content.strip()
            if not translated:
                log.warning("翻译返回空内容，使用原文")
                return text

            log.info("✅ 翻译完成")
            return translated

        except APITimeoutError:
            log.error("翻译 API 超时，返回原文")
            return text
        except APIConnectionError as e:
            log.error("翻译连接失败: %s，返回原文", e)
            return text
        except Exception as e:
            log.error("翻译失败: %s，返回原文", e)
            return text
