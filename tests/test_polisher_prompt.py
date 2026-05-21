from src.polisher import POLISH_SYSTEM_PROMPT, build_prompt


def test_default_prompt_includes_structure_without_forcing_summary():
    assert "编号列表" in POLISH_SYSTEM_PROMPT
    assert "自动分段" in POLISH_SYSTEM_PROMPT or "自动分段" in build_prompt()
    assert "只有当原文明确要求" in POLISH_SYSTEM_PROMPT
    assert "不要摘要或压缩信息" in POLISH_SYSTEM_PROMPT


def test_no_translation_prompt_keeps_language_guard():
    prompt = build_prompt()

    assert prompt.startswith("CRITICAL: Output language must match input language.")
    assert "Never translate." in prompt


def test_translation_prompt_preserves_terms_and_structure():
    prompt = build_prompt(translate_to="en")

    assert "只输出英语翻译结果" in prompt
    assert "保持相同编号结构" in prompt
    assert "API 字段" in prompt
    assert "禁止输出润色后的原文" in prompt


def test_translation_with_original_requires_two_blocks_without_labels():
    prompt = build_prompt(translate_to="zh", show_original=True)

    assert "必须同时输出两段" in prompt
    assert "空一行" in prompt
    assert "第一段为润色后的原文" in prompt
    assert "第二段为简体中文翻译" in prompt
    assert "禁止添加「原文：」「翻译：」" in prompt


def test_default_prompt_cleans_real_speech_artifacts():
    assert "输出应像整理过的一段文字" in POLISH_SYSTEM_PROMPT
    assert "比较比较比较重→比较重" in POLISH_SYSTEM_PROMPT
    assert "ton尼→Tony" in POLISH_SYSTEM_PROMPT
    assert "hand一下→handle 一下" in POLISH_SYSTEM_PROMPT
    assert "无法确定的人名、项目名、客户名、内部缩写只做排版清理" in POLISH_SYSTEM_PROMPT
