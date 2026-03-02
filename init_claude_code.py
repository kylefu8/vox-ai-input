import os
import json
import sys
import platform
import subprocess
import argparse


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def create_file(filepath, content):
    """创建目录并写入文件"""
    dirpath = os.path.dirname(filepath)
    if dirpath:
        os.makedirs(dirpath, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content.strip() + "\n")
    print(f"  ✅ {filepath}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第 1 步：环境安全检查
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_environment(target_dir):
    """检查 Python 版本、Claude Code 安装、目录冲突"""
    print("🔍 环境检查中...\n")
    all_ok = True

    # 1) Python 版本检查
    py_version = sys.version_info
    if py_version >= (3, 7):
        print(f"  ✅ Python 版本: {py_version.major}.{py_version.minor}.{py_version.micro}")
    else:
        print(f"  ❌ Python 版本过低: {py_version.major}.{py_version.minor}.{py_version.micro} (需要 >= 3.7)")
        print("     请升级 Python 后重试。")
        sys.exit(1)

    # 2) Claude Code 是否已安装
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            version_str = result.stdout.strip() or result.stderr.strip()
            print(f"  ✅ Claude Code: 已安装 ({version_str})")
        else:
            print("  ⚠️  Claude Code: 未检测到（不影响初始化，稍后可安装）")
            print("     安装命令: npm install -g @anthropic-ai/claude-code")
            all_ok = False
    except FileNotFoundError:
        print("  ⚠️  Claude Code: 未检测到（不影响初始化，稍后可安装）")
        print("     安装命令: npm install -g @anthropic-ai/claude-code")
        all_ok = False
    except Exception:
        print("  ⚠️  Claude Code: 检测超时，跳过")
        all_ok = False

    # 3) 目录冲突检测
    claude_md_path = os.path.join(target_dir, "CLAUDE.md")
    claude_dir_path = os.path.join(target_dir, ".claude")

    has_conflict = os.path.exists(claude_md_path) or os.path.exists(claude_dir_path)
    if has_conflict:
        existing = []
        if os.path.exists(claude_md_path):
            existing.append("CLAUDE.md")
        if os.path.exists(claude_dir_path):
            existing.append(".claude/")
        print(f"\n  ⚠️  目标目录已存在: {', '.join(existing)}")
        answer = input("     是否覆盖现有配置？(y/N): ").strip().lower()
        if answer != 'y':
            print("\n  ❎ 已取消，未做任何修改。")
            sys.exit(0)
        print("     ✅ 将覆盖现有配置")
    else:
        print(f"  ✅ 目标目录: {target_dir} (无冲突)")

    print()
    return all_ok


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第 2 步：交互式收集项目信息
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def collect_project_info(target_dir):
    """交互式引导用户填写项目信息"""
    print("📋 项目信息设置")
    print("━" * 36)

    # 默认项目名 = 目标目录的文件夹名
    default_name = os.path.basename(os.path.abspath(target_dir))

    # 1/3 项目名称
    name = input(f"  1/3 项目名称 (回车默认: {default_name}): ").strip()
    if not name:
        name = default_name

    # 2/3 项目目标
    goal = input("  2/3 用一句话描述项目目标 (回车跳过): ").strip()
    if not goal:
        goal = "[待补充：请描述项目目标]"

    # 3/3 当前阶段
    print("  3/3 当前阶段:")
    print("       [1] 早期开发 / 原型验证 (默认)")
    print("       [2] 活跃开发中")
    print("       [3] 维护 / 优化阶段")
    stage_input = input("       请选择 (1/2/3): ").strip()
    stage_map = {
        "1": "早期开发/原型验证阶段",
        "2": "活跃开发中",
        "3": "维护/优化阶段",
    }
    stage = stage_map.get(stage_input, stage_map["1"])

    print(f"\n  📝 项目名称: {name}")
    print(f"  📝 项目目标: {goal}")
    print(f"  📝 当前阶段: {stage}")
    print()

    return {"name": name, "goal": goal, "stage": stage}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第 3 步：生成所有配置文件
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def init_claude_project(project_info):
    """根据收集到的项目信息，生成 Claude Code 配置文件"""
    print("📦 正在生成配置文件...\n")

    # ── 1. CLAUDE.md ──
    claude_md = f"""
# {project_info['name']}

{project_info['goal']}

## 技术栈
- [待补充：语言/框架/主要依赖]

## 跨平台约束
- 本项目在 macOS ARM64 和 Windows x86_64 上交替开发
- 执行命令前先检测当前 OS（详见 .claude/rules/memory-preferences.md）

## 工作方式
- 实质性改动前先输出步骤计划，等我确认后再动手
- 遇到不确定的问题，优先用工具查阅或问我
- 用中文和我沟通

## 常用命令
（首次使用时请补充实际命令，删除本行提示）

## 代码风格
- 使用 4 空格缩进
- 变量/函数用 snake_case，类用 PascalCase
- 每个函数和类都要有 docstring

## Git 规范
- commit message 使用中文，格式: `<类型>: <简述>`（类型: feat/fix/refactor/docs/chore）
- 每次 commit 只做一件事

## 记忆系统
.claude/rules/ 目录下的文件会自动加载，包含环境信息、开发偏好、技术决策和会话进度。
当学到新信息时，按以下规则直接更新对应文件，无需询问：
- 用户偏好/习惯 → memory-preferences.md
- 技术选型/架构决策 → memory-decisions.md
- 任务完成/里程碑 → memory-sessions.md
"""
    create_file("CLAUDE.md", claude_md)

    # ── 2. memory-profile.md（使用收集到的项目信息）──
    profile_md = f"""
# 运行环境与项目基调

## 🖥️ 跨平台硬件环境 (Dual-Environment Setup)
本项目在两套物理系统上交替运行，代码和配置必须保持跨平台兼容：
- **环境 A (Apple Silicon)**: Mac Mini (M4芯片, ARM64架构, macOS)。默认终端为 zsh/bash。
- **环境 B (Windows)**: 基于 x86_64 架构的 Windows 系统。默认终端为 PowerShell。

## 🎯 项目概览
- **项目名称**: {project_info['name']}
- **核心目标**: {project_info['goal']}
- **当前阶段**: {project_info['stage']}
"""
    create_file(".claude/rules/memory-profile.md", profile_md)

    # ── 3. memory-preferences.md ──
    prefs_md = """
# 开发偏好与沟通习惯

## 🗣️ 沟通方式 (Vibe Coding Friendly)
- **通俗易懂**: 我不需要生涩的计算机术语。请用清晰的逻辑向我解释"为什么"要这么写代码，以及这段代码是做什么的。
- **提供选项**: 遇到需要做技术选择时（例如选择第三方库），请列出 2-3 个对新手友好的选项，简述优缺点，由我来决定。

## 💻 跨平台代码规范 (Cross-Platform Coding)
- **路径处理**: 绝对不要在代码中硬编码带有斜杠的字符串路径。必须使用标准库（如 Python 的 `os.path` 或 `pathlib`，Node.js 的 `path` 模块）来处理路径，确保在 Mac 和 Windows 上都能直接运行。
- **依赖兼容性**: 引入新依赖时，请主动核实其是否同时良好支持 macOS ARM64 和 Windows x86_64。

## 🛡️ 防御性编程
- 优先编写包含丰富错误捕获（try-catch / try-except）的代码。
- 增加清晰的控制台日志（log/print），当程序在任一系统上报错时，能让我一眼看出问题出在哪一步。
"""
    create_file(".claude/rules/memory-preferences.md", prefs_md)

    # ── 4. memory-decisions.md ──
    decisions_md = """
# 架构与技术决策日志

*说明：每次确认采用某个重要框架、库或项目结构调整时，必须在此记录，并标明日期，以保持全局一致性。*

## 已确认的决策
- [x] 确立了跨平台（Mac ARM64 + Windows x86_64）的双端开发标准。
- [ ] *[待补充：记录你未来决定的技术栈，例如 Python 版本、框架选择等]*
"""
    create_file(".claude/rules/memory-decisions.md", decisions_md)

    # ── 5. memory-sessions.md ──
    sessions_md = f"""
# 会话进度与备忘录 (Kanban)

## 📍 当前主要目标 (North Star)
{project_info['goal']}

## ✅ 已完成 (Recently Completed)
- 运行了初始化脚本，生成了包含路由、记忆更新指令和兜底机制的完整配置。

## 🚧 正在进行 (In Progress)
- [待补充：当前正在进行的具体任务]

## 📌 下一步 (Next Steps / Backlog)
1. 启动 Claude Code，运行 /memory 和 /hooks 验证配置是否正确加载。
2. [待补充：后续计划]
"""
    create_file(".claude/rules/memory-sessions.md", sessions_md)

    # ── 6. Stop Hook 脚本 ──
    hook_py = """
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
"""
    create_file(".claude/hooks/stop_hook.py", hook_py)

    # ── 7. settings.json ──
    # 使用官方要求的嵌套数组格式，根据操作系统选择 python/python3 命令
    py_cmd = "python" if platform.system() == "Windows" else "python3"
    settings_json = {
        "hooks": {
            "Stop": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'{py_cmd} "$CLAUDE_PROJECT_DIR/.claude/hooks/stop_hook.py"'
                        }
                    ]
                }
            ]
        }
    }

    os.makedirs(".claude", exist_ok=True)
    with open(".claude/settings.json", "w", encoding="utf-8") as f:
        json.dump(settings_json, f, indent=2, ensure_ascii=False)
    print("  ✅ .claude/settings.json")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 第 4 步：完成提示
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def print_summary(target_dir):
    """打印初始化完成后的总结信息"""
    print("\n" + "━" * 40)
    print("🎉 初始化完成！")
    print("━" * 40)
    print(f"  📁 项目目录: {os.path.abspath(target_dir)}")
    print()
    print("  生成的文件:")
    print("  ├── CLAUDE.md                    (项目路由)")
    print("  └── .claude/")
    print("      ├── settings.json            (Hook 配置)")
    print("      ├── rules/")
    print("      │   ├── memory-profile.md     (环境信息)")
    print("      │   ├── memory-preferences.md (开发偏好)")
    print("      │   ├── memory-decisions.md   (技术决策)")
    print("      │   └── memory-sessions.md    (会话进度)")
    print("      └── hooks/")
    print("          └── stop_hook.py          (停止提醒)")
    print()
    print("  👉 下一步:")
    print(f"     cd \"{os.path.abspath(target_dir)}\"")
    print("     claude")
    print()
    print("  🔍 进入 Claude Code 后，可运行以下命令验证:")
    print("     /memory   ← 查看记忆文件是否全部加载")
    print("     /hooks    ← 查看 Hook 是否注册成功")
    print("━" * 40)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    parser = argparse.ArgumentParser(
        description="🚀 Claude Code 项目初始化工具 — 一键生成跨平台配置"
    )
    parser.add_argument(
        "--dir",
        default=".",
        help="目标项目目录 (默认: 当前目录)"
    )
    args = parser.parse_args()

    target_dir = os.path.abspath(args.dir)

    print()
    print("🚀 Claude Code 项目初始化工具")
    print("━" * 40)
    print(f"  目标目录: {target_dir}")
    print()

    # 确保目标目录存在
    if not os.path.isdir(target_dir):
        print(f"  ❌ 目标目录不存在: {target_dir}")
        answer = input("     是否自动创建？(y/N): ").strip().lower()
        if answer == 'y':
            os.makedirs(target_dir, exist_ok=True)
            print(f"  ✅ 已创建目录: {target_dir}")
            print()
        else:
            print("\n  ❎ 已取消。")
            sys.exit(0)

    # 第 1 步：环境检查
    check_environment(target_dir)

    # 第 2 步：交互式收集项目信息
    project_info = collect_project_info(target_dir)

    # 第 3 步：切换到目标目录并生成文件
    os.chdir(target_dir)
    init_claude_project(project_info)

    # 第 4 步：完成提示
    print_summary(target_dir)


if __name__ == "__main__":
    main()
