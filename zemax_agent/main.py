"""Zemax OpticStudio AI Agent — 统一程序入口.

用法:
    python main.py                  # 启动 CLI AI 助手（默认）
    python main.py --mcp            # 启动 MCP 服务器（供 VS Code / Claude Desktop 使用）
    python main.py --setup          # 交互式配置向导（首次使用推荐）
    python main.py --clear-cache    # 清理 gen_py 缓存后启动
    python main.py --help           # 详细帮助
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
#  路径常量 — 打包后路径与开发路径兼容
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent.resolve()
_PROJECT_ROOT = _HERE.parent if (_HERE.parent / ".git").exists() else _HERE
_ENV_PATH = _HERE / ".env"

# ---------------------------------------------------------------------------
#  加载 .env（放在最前面，其余模块依赖环境变量）
# ---------------------------------------------------------------------------

from dotenv import load_dotenv

load_dotenv(_ENV_PATH)

# ---------------------------------------------------------------------------
#  sys.path 确保同目录模块可用（打包时也如此）
# ---------------------------------------------------------------------------

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# ---------------------------------------------------------------------------
#  日志（在所有业务模块之前初始化）
# ---------------------------------------------------------------------------

from logger import logger

# ---------------------------------------------------------------------------
#  业务模块
# ---------------------------------------------------------------------------

from openai import OpenAI

from tools import TOOL_DEFINITIONS, ZemaxToolkit
from zemax_connection import ZemaxConnection

# ---------------------------------------------------------------------------
#  Skill 加载 — 从 SKILL.md 注入领域知识
# ---------------------------------------------------------------------------

_SKILL_CANDIDATES = [
    _PROJECT_ROOT / ".github" / "skills" / "zemax-optical-design" / "SKILL.md",
    _HERE / "SKILL.md",
    _HERE / "skills" / "SKILL.md",
]


def _load_skill() -> str:
    """尝试加载 SKILL.md，返回剥离 YAML frontmatter 后的内容；未找到则返回空字符串."""
    for path in _SKILL_CANDIDATES:
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                logger.info(f"已加载技能文件: {path}")
                # 去掉 YAML frontmatter（--- ... ---）
                if content.startswith("---"):
                    end = content.find("---", 3)
                    if end != -1:
                        content = content[end + 3:].strip()
                return content
            except Exception as e:
                logger.warning(f"读取技能文件失败: {path}: {e}")
    logger.warning("未找到 SKILL.md，AI 将在无领域增强的基础模式下运行")
    return ""


# ---------------------------------------------------------------------------
#  系统提示词
# ---------------------------------------------------------------------------

_SYSTEM_BASE = """\
你是一个专业的 Zemax OpticStudio 光学设计助手。你通过工具函数与 OpticStudio 交互，帮助用户完成光学系统的设计与优化。

你的能力包括：
- 查看当前光学系统信息（表面、光圈、视场、波长）
- 创建和编辑光学表面（设置曲率半径、厚度、材料、半口径、圆锥系数等）
- 设置系统参数（光圈、视场、波长）
- 评价函数管理：用向导设置默认评价函数、手动添加/删除操作数（EFFL、BFL、TOTR 等）、查看操作数详情
- 系统性能分析：计算有效焦距、后焦距、总长等一阶光学参数
- 将参数设为变量并运行优化（局部优化、快速聚焦）
- 文件管理（新建、打开、保存）
- 打开 2D/3D 布局图，优化后实时刷新 GUI

核心操作规范：
1. **保护用户已有设计**：执行任何操作前，先用 get_system_info 查看当前系统状态。
   如果系统中已有表面/透镜数据，绝不能在未经用户明确确认的情况下调用 new_file 清除它们。
2. 修改系统后，简要报告所做的更改。
3. 对于不确定的参数，先询问用户。
4. 使用专业但易懂的光学术语。
5. 表面编号从 0 开始：0 = 物面 (OBJ)，最后一个 = 像面 (IMA)。
6. 曲率半径单位为 mm，波长单位为 μm。
7. 如果工具返回错误，分析错误原因后尝试换一种方式，不要无限重试同一操作。
8. **绝不要在用户没有明确要求的情况下调用 new_file**。当用户问"看看当前系统"或类似问题时，
   只需调用 get_system_info 读取并报告，不要创建新系统。

优化工作流建议：
1. 先用 get_system_info 了解当前系统
2. 用 set_default_merit_function 设置基本评价函数（如 RMS 光斑半径）
3. 如需约束焦距等参数，用 add_operand 添加 EFFL 等操作数并设置目标值和权重
4. 用 make_variable 设置需要优化的参数为变量
5. 用 run_optimization 运行优化
6. 用 get_first_order_data 查看优化后的系统性能
7. 用 get_operands 查看评价函数各项指标

注意：你只能通过提供的工具与 OpticStudio 交互，不能直接修改任何数据。
"""


def _build_system_prompt() -> str:
    """构建最终系统提示词 = 基础提示 + SKILL.md 领域知识."""
    skill_content = _load_skill()
    if skill_content:
        return (
            _SYSTEM_BASE
            + "\n\n---\n\n## 领域知识库（光学设计经验速查）\n\n"
            + skill_content
        )
    return _SYSTEM_BASE


# ---------------------------------------------------------------------------
#  交互式配置向导
# ---------------------------------------------------------------------------


def run_setup_wizard():
    """首次运行引导：交互式生成 .env 配置文件."""
    print("\n" + "=" * 60)
    print("  Zemax OpticStudio AI Agent — 初始配置向导")
    print("=" * 60)
    print(f"\n配置文件将保存到: {_ENV_PATH}")
    print("直接回车使用 [方括号] 内的默认值\n")

    def ask(prompt: str, default: str = "", secret: bool = False) -> str:
        display = default
        if secret and default and default != "your-api-key-here":
            display = default[:4] + "****"
        hint = f" [{display}]" if display else ""
        val = input(f"  {prompt}{hint}: ").strip()
        return val or default

    print("─── LLM API 配置 ───────────────────────────────────────")
    print("  支持任何 OpenAI 兼容 API（DeepSeek / Qwen / 本地 Ollama 等）")
    print()
    api_key = ask("API Key（必填）", secret=True)
    base_url = ask("API Base URL", "https://api.deepseek.com/v1")
    model = ask("Model Name", "deepseek-chat")

    print("\n─── Zemax 连接配置 ──────────────────────────────────────")
    print("  extension : 连接到已运行的 OpticStudio（推荐，需先点 Interactive Extension）")
    print("  standalone: 让 Python 直接启动新的 OpticStudio 实例")
    zemax_mode = ask("连接模式 (extension/standalone)", "extension")
    instance = ask("Extension 实例编号", "0")

    content = (
        "# LLM API 配置\n"
        f"OPENAI_API_KEY={api_key}\n"
        f"OPENAI_BASE_URL={base_url}\n"
        f"MODEL_NAME={model}\n"
        "\n"
        "# Zemax 连接模式: extension (连接到运行中的OpticStudio) 或 standalone\n"
        f"ZEMAX_MODE={zemax_mode}\n"
        "# Extension 实例编号 (默认0)\n"
        f"ZEMAX_INSTANCE={instance}\n"
    )

    _ENV_PATH.write_text(content, encoding="utf-8")
    print(f"\n\033[32m✓ 配置已保存到 {_ENV_PATH}\033[0m")
    print("\n接下来:")
    print("  python main.py          # 启动 CLI AI 助手")
    print("  python main.py --mcp    # 启动 MCP 服务器（供 VS Code / Claude Desktop 使用）")


# ---------------------------------------------------------------------------
#  帮助文本
# ---------------------------------------------------------------------------


def _print_help():
    print("""
\033[33m常用指令示例:\033[0m
  查看系统     → "显示当前光学系统状态"
  新建系统     → "新建一个空白系统"
  设置波长     → "设置 F / d / C 三色光波长"
  设置光圈     → "设置入瞳直径为 20mm"
  插入表面     → "在第2面后插入一个新表面"
  编辑表面     → "将第1面曲率改为 52mm，材料设为 N-BK7"
  打开布局     → "打开2D布局图"
  优化         → "把所有曲率作为变量，运行 DLS 优化"
  验证结果     → "查看系统焦距和总长"
  保存文件     → "保存为 C:/Zemax/Samples/doublet.zmx"

\033[33m内置命令:\033[0m
  reconnect    重新连接 OpticStudio
  clear        清空对话历史（不影响 OpticStudio 中的系统）
  help         显示本帮助
  quit/exit/q  退出程序
""")


# ---------------------------------------------------------------------------
#  Agent 主循环
# ---------------------------------------------------------------------------


def run_agent(client: OpenAI, model: str, toolkit: ZemaxToolkit):
    """运行 CLI Agent 的交互循环."""
    system_prompt = _build_system_prompt()
    messages = [{"role": "system", "content": system_prompt}]

    logger.info(f"CLI Agent 启动，模型: {model}")

    print("\n" + "=" * 60)
    print("  Zemax OpticStudio AI 助手")
    print("  输入自然语言指令与 OpticStudio 交互")
    print("  输入 'help' 查看常用示例，'quit' 退出")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("\033[36m你> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            logger.info("用户中断，退出 CLI Agent")
            break

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            logger.info("用户主动退出 CLI Agent")
            break

        # ---- 内置命令 ----
        if user_input.lower() == "reconnect":
            print("\033[33m正在重连 OpticStudio...\033[0m")
            logger.info("用户触发手动重连")
            if toolkit.conn.reconnect():
                print("\033[32m重连成功！\033[0m\n")
                logger.info("手动重连成功")
            else:
                print("\033[31m重连失败。请确保 OpticStudio 已打开 Interactive Extension。\033[0m\n")
                logger.warning("手动重连失败")
            continue

        if user_input.lower() == "clear":
            messages = [{"role": "system", "content": system_prompt}]
            print("\033[33m对话历史已清空。\033[0m\n")
            logger.info("对话历史已清空")
            continue

        if user_input.lower() == "help":
            _print_help()
            continue

        logger.info(f"用户输入: {user_input[:200]}")
        messages.append({"role": "user", "content": user_input})

        # Agent 循环：可能需要多轮工具调用
        while True:
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                )
            except Exception as e:
                print(f"\033[31m[LLM 请求失败] {e}\033[0m")
                logger.error(f"LLM 请求失败: {e}", exc_info=True)
                messages.pop()
                break

            choice = response.choices[0]
            assistant_msg = choice.message
            messages.append(_message_to_dict(assistant_msg))

            if assistant_msg.tool_calls:
                for tool_call in assistant_msg.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}

                    logger.info(f"工具调用: {fn_name}({_brief_args(fn_args)})")
                    print(f"\033[33m  [调用工具] {fn_name}({_brief_args(fn_args)})\033[0m")
                    result = toolkit.dispatch(fn_name, fn_args)
                    logger.debug(f"工具结果: {result[:500]}")
                    print(f"\033[90m  [结果] {_truncate(result, 200)}\033[0m")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                continue
            else:
                reply = assistant_msg.content or ""
                logger.info(f"助手回复: {reply[:300]}")
                print(f"\033[32m助手> {reply}\033[0m\n")
                break


# ---------------------------------------------------------------------------
#  MCP 服务器模式
# ---------------------------------------------------------------------------


def run_mcp_mode(zemax_mode: str, instance: int, clear_cache: bool):
    """以 MCP stdio 服务器模式运行（替换当前进程）."""
    logger.info(f"切换到 MCP 服务器模式: zemax_mode={zemax_mode}, instance={instance}")
    mcp_script = _HERE / "mcp_server.py"
    if not mcp_script.exists():
        print(f"\033[31m错误: 找不到 mcp_server.py ({mcp_script})\033[0m")
        sys.exit(1)
    cmd = [sys.executable, str(mcp_script),
           "--zemax-mode", zemax_mode,
           "--instance", str(instance)]
    if clear_cache:
        cmd.append("--clear-cache")
    # 用 MCP 服务器进程替换当前进程（exec-style，Windows 下用 execv 模拟）
    os.execv(sys.executable, cmd)


# ---------------------------------------------------------------------------
#  辅助函数
# ---------------------------------------------------------------------------


def _message_to_dict(msg) -> dict:
    """将 OpenAI Message 对象转为可序列化的 dict."""
    d = {"role": msg.role, "content": msg.content}
    if msg.tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return d


def _brief_args(args: dict, max_len=80) -> str:
    s = ", ".join(f"{k}={v!r}" for k, v in args.items())
    return s[:max_len] + "..." if len(s) > max_len else s


def _truncate(s: str, max_len: int) -> str:
    return s[:max_len] + "..." if len(s) > max_len else s


def _print_env_template():
    print("""\033[90m# zemax_agent/.env
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
ZEMAX_MODE=extension
ZEMAX_INSTANCE=0\033[0m""")


# ---------------------------------------------------------------------------
#  入口
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Zemax OpticStudio AI Agent — 统一入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py                          # 启动 CLI AI 助手（默认）
  python main.py --mcp                    # 启动 MCP 服务器
  python main.py --setup                  # 运行配置向导（首次使用）
  python main.py --model deepseek-chat    # 临时指定模型
  python main.py --clear-cache            # 清理 gen_py 缓存后启动
        """,
    )
    parser.add_argument(
        "--mcp", action="store_true",
        help="以 MCP stdio 服务器模式启动（供 VS Code / Claude Desktop 使用）",
    )
    parser.add_argument(
        "--setup", action="store_true",
        help="运行交互式配置向导，生成 .env 文件",
    )
    parser.add_argument("--api-key", type=str, help="LLM API Key（覆盖 .env）")
    parser.add_argument("--base-url", type=str, help="LLM API Base URL（覆盖 .env）")
    parser.add_argument("--model", type=str, help="模型名称（覆盖 .env）")
    parser.add_argument(
        "--zemax-mode",
        type=str,
        choices=["extension", "standalone"],
        default=None,
        help="Zemax 连接模式（覆盖 .env）",
    )
    parser.add_argument("--instance", type=int, default=None, help="Extension 实例编号")
    parser.add_argument(
        "--clear-cache", action="store_true",
        help="启动前清理 win32com gen_py ZOSAPI 缓存（遇到 COM 类型错误时使用）",
    )
    args = parser.parse_args()

    # ── 配置向导模式 ──────────────────────────────────────────────────────
    if args.setup:
        run_setup_wizard()
        return

    # ── 读取配置（优先级: 命令行 > .env > 默认值）────────────────────────
    if not _ENV_PATH.exists() and not args.api_key:
        print("\033[33m⚠ 未找到 .env 配置文件。\033[0m")
        print("\n推荐运行配置向导:")
        print("  python main.py --setup")
        print("\n或手动创建 zemax_agent/.env 文件，参考模板:\n")
        _print_env_template()
        sys.exit(1)

    api_key = args.api_key or os.getenv("OPENAI_API_KEY", "")
    base_url = args.base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = args.model or os.getenv("MODEL_NAME", "gpt-4")
    zemax_mode = args.zemax_mode or os.getenv("ZEMAX_MODE", "extension")
    instance = args.instance if args.instance is not None else int(os.getenv("ZEMAX_INSTANCE", "0"))

    # ── MCP 服务器模式 ────────────────────────────────────────────────────
    if args.mcp:
        run_mcp_mode(zemax_mode, instance, args.clear_cache)
        return  # os.execv 不会返回此处

    # ── CLI AI 助手模式 ───────────────────────────────────────────────────
    if not api_key or api_key == "your-api-key-here":
        print("\033[31m错误: 未配置 API Key。\033[0m")
        print("运行配置向导: python main.py --setup")
        print("或手动编辑 zemax_agent/.env 中的 OPENAI_API_KEY")
        sys.exit(1)

    # 可选: 清理 gen_py 缓存
    if args.clear_cache:
        print("正在清理 ZOSAPI gen_py 缓存...")
        logger.info("用户请求清理 gen_py 缓存")
        try:
            ZemaxConnection.clear_gen_py_cache()
            print("\033[32m✓ 缓存已清理。\033[0m")
            logger.info("gen_py 缓存清理完成")
        except Exception as e:
            print(f"\033[33m缓存清理失败（非致命）: {e}\033[0m")
            logger.warning(f"gen_py 缓存清理失败: {e}")

    # 初始化 LLM 客户端
    logger.info(f"初始化 LLM 客户端: base_url={base_url}, model={model}")
    print(f"\033[90mLLM: {base_url}  model={model}\033[0m")
    client = OpenAI(api_key=api_key, base_url=base_url)

    # 连接 Zemax
    print(f"正在连接 OpticStudio（模式: {zemax_mode}, 实例: {instance}）...")
    logger.info(f"连接 OpticStudio: mode={zemax_mode}, instance={instance}")
    conn = ZemaxConnection()
    try:
        conn.connect(mode=zemax_mode, instance=instance)
    except Exception as e:
        print(f"\033[31m连接 OpticStudio 失败: {e}\033[0m")
        logger.error(f"连接 OpticStudio 失败: {e}", exc_info=True)
        print("\n请确保:")
        print("  1. Zemax OpticStudio 正在运行")
        print("  2. 已点击 Programming → Interactive Extension")
        print("  3. 若仍失败，尝试: python main.py --clear-cache")
        sys.exit(1)

    logger.info(f"OpticStudio 连接成功，序列号: {conn.app.SerialCode}")
    print(f"\033[32m✓ 已连接到 OpticStudio（序列号: {conn.app.SerialCode}）\033[0m")

    wl_cache = conn._prop_cache.get("IWavelength", {})
    fl_cache = conn._prop_cache.get("IField", {})
    logger.debug(
        f"属性映射诊断: IWavelength.value='{wl_cache.get('value')}', "
        f"IField.x='{fl_cache.get('x')}'"
    )

    toolkit = ZemaxToolkit(conn)

    try:
        run_agent(client, model, toolkit)
    finally:
        conn.disconnect()
        logger.info("已断开 OpticStudio 连接")
        print("已断开 OpticStudio 连接。")


if __name__ == "__main__":
    main()
