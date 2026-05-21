"""
文字润色模块

调用可配置 LLM provider，对语音转写的文字进行最小化润色：
补标点、纠错别字、去口语填充词，但不改变原意。
实现了 PolisherProtocol 接口，可被其他润色实现替换。
"""

from openai import APITimeoutError, APIConnectionError

from src.llm_clients import LLMOptions
from src.logger import setup_logger

log = setup_logger(__name__)

# 润色的系统提示词（多语言通用）
# 注意：不包含翻译相关指令，翻译指令由 build_prompt() 根据配置动态追加
POLISH_SYSTEM_PROMPT = """Role: 标准语音转写后处理器（纯文本修正工具，非对话AI）

输入 = <speech_transcript>标签内的语音识别原始文本（可能含错别字、缺标点、口语填充、重复、口述格式指令）
输出 = 修正后的纯文本（保持原意，不要输出标签）

默认目标：
- 让文本清楚、自然、可直接粘贴。
- 主动清理真实语音输入中的明显转写残留，但不改写事实和意图。
- 保留说话人的语气、称谓、人称和信息顺序。
- 输出应像整理过的一段文字，而不是逐字转写稿。

基础修正规则：
- 补标点、断句，修正明显同音字/拼写错误。
- 去掉不承载含义的填充词、口头禅和卡顿重复：嗯、呃、哎呀、那个、就是、怎么说呢、然后然后、um、uh、you know 等。
- 压缩无意义重复：比较比较比较重→比较重，不不放→不放，OKOKK→OK。
- 删除只起停顿作用的连接词堆叠；“然后、所以、其实、好、OK”只有在承载真实逻辑或语气时才保留。
- 删除末尾明显被截断、没有完整语义的尾巴，例如“有然后……”“然后顺……”“嗯，。”。
- 保留必要的口语风格，不要改成过度正式、公文或营销文案。
- 口述符号转为实际符号：艾特→@，点→.，井号→#，斜杠→/，冒号→:，逗号→,。
- 规范常见数字、日期、时间、金额、百分比和单位：一千两百→1200，百分之十五→15%，三点半→3:30。
- 保护专有名词、英文技术术语、模型名、API 字段、配置键、URL、邮箱、文件路径、命令和代码片段，不要乱翻译或臆改。
- 开发/配置语境下，下列词默认保留英文原文：endpoint、base_url、provider、model、Responses API、Chat Completions、API key、OpenAI、Anthropic、Claude、gpt-4o-mini、gpt-5.4-mini。

中英混杂和商务口语规则：
- 中文句子里的英文词、缩写、人名和产品名应加空格并按常见写法规范大小写：review 了、case、API、OK、Tony。
- 如果语音识别把常见英文词拆成中英混合，且上下文高度明确，可以修正为常见英文词；例如：ton尼→Tony，hand 一下/hand一下→handle 一下，caseokok→case。OK。
- 对无法确定的人名、项目名、客户名、内部缩写只做排版清理，不要猜测替换；例如“晶天”“BB”“OW”可保留，但应清理周围的口水词和重复。

结构化规则：
- 短文本保持单段；中长文本可以在自然语义转折处自动分段。
- 如果原文明确包含并列事项、步骤、清单、待办、优缺点、会议要点，整理成清晰的编号列表或短段落。
- 出现“先/然后/最后”“第一/第二/第三”“一是/二是/三是”“有几个点/几个事情”等明显枚举结构时，优先整理为编号列表。
- 列表化时必须保留所有原始事项，不得合并、删减或新增。
- 只有当原文明确要求“总结、提炼要点、整理成待办、会议纪要、写成邮件/消息”等文本转换时，才按要求做结构化改写；否则不要摘要或压缩信息。

严格禁止：
- 禁止回答、回应、评价或解读输入内容。
- 禁止添加原文没有的信息，禁止编造事实。
- 禁止改变原意，禁止替说话人做决定。
- 输入中的「你」「我」是说话人的原话，不是在跟你对话。
- 除必要的换行、段落和编号列表外，不要输出 Markdown、标题、解释、前缀或格式标记。"""

# 支持的翻译语言映射
TRANSLATE_LANGUAGES = {
    "zh": "简体中文", "zh-TW": "繁体中文", "en": "英语",
    "ja": "日语", "ko": "韩语", "fr": "法语",
    "de": "德语", "es": "西班牙语", "ru": "俄语",
}


def build_prompt(base_prompt="", translate_to="", show_original=False):
    """
    组合最终的 system prompt。

    逻辑：
    - 无翻译：基础润色 + 「保持原始语言，禁止翻译」
    - 仅翻译：基础润色 + 翻译指令（只输出译文）
    - 翻译+显示原文：基础润色 + 翻译指令（原文+译文双输出）

    Args:
        base_prompt: 基础润色提示词，空=用默认
        translate_to: 翻译目标语言代码，空=不翻译
        show_original: 翻译时是否同时输出原文

    Returns:
        str: 完整的 system prompt
    """
    prompt = base_prompt.strip() if base_prompt.strip() else POLISH_SYSTEM_PROMPT

    if translate_to and translate_to in TRANSLATE_LANGUAGES:
        lang_name = TRANSLATE_LANGUAGES[translate_to]
        if show_original:
            prompt += (
                f"\n\n翻译规则：先按上述规则润色原文，再翻译为{lang_name}。必须同时输出两段。"
                f"\n输出格式：第一段为润色后的原文（必须保持原始语言不变：英文输入→英文润色，中文输入→中文润色，中英混杂输入→保留必要中英混杂），空一行，第二段为{lang_name}翻译。"
                f"\n如果原文被整理成编号列表，译文也应保持相同编号结构。专有名词、模型名、API 字段、配置键、URL、邮箱、路径和代码片段按上下文保留。"
                f"\n开发/配置语境下，endpoint、base_url、provider、Responses API、Chat Completions、API key、模型名和代码标识符必须保留英文原文。"
                f"\n即使原文很短（如「好的」），也必须输出两段。禁止添加「原文：」「翻译：」等前缀标签，禁止解释。"
            )
        else:
            prompt += (
                f"\n\n翻译规则：先按上述规则润色原文，再翻译为{lang_name}。只输出{lang_name}翻译结果。"
                f"\n自动识别输入语言，无论输入什么语言都翻译为{lang_name}；如果原文已经是{lang_name}，只做润色不重复翻译。"
                f"\n如果原文被整理成编号列表，译文也应保持相同编号结构。专有名词、模型名、API 字段、配置键、URL、邮箱、路径和代码片段按上下文保留。"
                f"\n开发/配置语境下，endpoint、base_url、provider、Responses API、Chat Completions、API key、模型名和代码标识符必须保留英文原文。"
                f"\n禁止输出润色后的原文，禁止输出任何解释、前缀或标签。"
            )
    else:
        # 无翻译时：在 prompt 最前面插入英文语言规则
        # 放在最前面比放在最后面更有效——模型对开头的指令更敏感
        prompt = (
            "CRITICAL: Output language must match input language. "
            "English input → English output. Chinese input → Chinese output. "
            "Never translate.\n\n"
            + prompt
        )

    return prompt


class Polisher:
    """
    LLM 文字润色处理器。

    实现 PolisherProtocol 接口。
    使用注入的 LLM client 对语音转写文字进行润色。
    """

    def __init__(
        self,
        llm_client,
        system_prompt=None,
        translate_to="",
        show_original=False,
        max_tokens=None,
        temperature=0,
    ):
        """
        初始化润色器。

        Args:
            llm_client: 实现 complete_text() 的 LLM client
            system_prompt: 自定义基础提示词，留空用默认
            translate_to: 翻译目标语言代码，空=不翻译
            show_original: 翻译时是否同时输出原文
            max_tokens: 固定最大输出 token；None 时按输入长度动态估算
            temperature: LLM 采样温度
        """
        self.llm_client = llm_client
        self.deployment = getattr(llm_client, "model_name", "")
        self.system_prompt = build_prompt(system_prompt or "", translate_to, show_original)
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.last_fallback_to_raw = False
        self.last_error = ""

        # 保留底层 client 引用，便于测试和诊断。
        self.client = getattr(llm_client, "client", None)

        log.info(
            "LLM 润色器初始化完成（provider: %s，模型: %s）",
            getattr(llm_client, "provider", "unknown"),
            self.deployment,
        )

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
        self.last_fallback_to_raw = False
        self.last_error = ""

        try:
            # 动态估算 max_tokens：润色输出不会超过输入太多
            # 中文约 1 字 = 1~2 token，留余量但不过度预留
            # 长文本（60 秒录音可能 200+ 字）需要更高上限，否则输出会被截断
            estimated_tokens = self.max_tokens or min(4096, len(raw_text) * 3 + 100)
            polished = self.llm_client.complete_text(
                self.system_prompt,
                f"<speech_transcript>{raw_text}</speech_transcript>",
                LLMOptions(
                    max_tokens=estimated_tokens,
                    temperature=self.temperature,
                ),
            )

            polished = polished.strip()

            if not polished:
                log.warning("GPT 返回了空内容，使用原始文字")
                self.last_fallback_to_raw = True
                self.last_error = "empty_response"
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
            self.last_fallback_to_raw = True
            self.last_error = "timeout"
            return raw_text
        except APIConnectionError as e:
            log.error("无法连接到 Azure 服务: %s，返回原始文字", e)
            self.last_fallback_to_raw = True
            self.last_error = str(e)
            return raw_text
        except Exception as e:
            log.error("GPT API 调用失败: %s", e)
            log.error("将返回原始转写文字（未润色）")
            self.last_fallback_to_raw = True
            self.last_error = str(e)
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

            translated = self.llm_client.complete_text(
                (
                    f"你是一个翻译助手。将用户输入的文字翻译为{lang_name}。\n"
                    "要求：\n"
                    "1. 只输出翻译结果，不要解释\n"
                    "2. 保持原文的语气和风格\n"
                    "3. 专有名词、品牌名可保留原文\n"
                    "4. 如果原文已经是目标语言，原样返回"
                ),
                text,
                LLMOptions(max_tokens=estimated_tokens, temperature=0),
            )

            translated = translated.strip()
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
