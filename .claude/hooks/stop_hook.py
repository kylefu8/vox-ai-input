import sys
import re
import json

def main():
    try:
        # 读取 Claude Code 通过 stdin 传入的 JSON 上下文
        input_data = sys.stdin.read()
        context_obj = json.loads(input_data) if input_data.strip() else {}
        # 将整个输入转为字符串用于关键词匹配
        context = json.dumps(context_obj, ensure_ascii=False)
    except Exception:
        context = ""

    # 强信号词：修复、发现、顿悟
    strong_patterns = re.compile(
        r"fixed|workaround|gotcha|that's wrong|check again|we already|should have|discovered|realized|turns out|"
        r"修复|原来如此|发现了|搞错了|绕过|搞定了|终于",
        re.IGNORECASE
    )

    # 弱信号词：报错、问题
    weak_patterns = re.compile(
        r"error|bug|issue|problem|fail|"
        r"报错|错误|问题|失败",
        re.IGNORECASE
    )

    # Stop hook 输出格式：
    # - 不阻止停止时：直接 print 文本到 stdout（exit code 0），消息显示在 transcript 中
    # - 阻止停止时：输出 {"decision": "block", "reason": "..."}
    if strong_patterns.search(context):
        print("💡 本次会话包含修复或新发现，请主动将学到的知识更新到 .claude/rules 目录下的对应 memory 文档中。")
    elif weak_patterns.search(context):
        print("📝 如果本次会话学到了非显而易见的知识，请更新到 memory 文档中。")

    # exit code 0 = 不阻止停止，消息仅作为提示
    sys.exit(0)

if __name__ == "__main__":
    main()
