"""Zemax OpticStudio AI Agent — CLI 入口."""

import argparse
import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from tools import TOOL_DEFINITIONS, ZemaxToolkit
from zemax_connection import ZemaxConnection

# ---------------------------------------------------------------------------
#  系统提示词
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
你是一个专业的 Zemax OpticStudio 光学设计助手。你通过工具函数与 OpticStudio 交互，帮助用户完成光学系统的设计与优化。

你的能力包括：
- 查看当前光学系统信息（表面、光圈、视场、波长）
- 创建和编辑光学表面（设置曲率半径、厚度、材料、半口径、圆锥系数等）
- 设置系统参数（光圈、视场、波长）
- 将参数设为变量并运行优化
- 文件管理（新建、打开、保存）

操作规范：
1. 执行操作前，先用 get_system_info 了解当前系统状态
2. 修改系统后，简要报告所做的更改
3. 对于不确定的参数，先询问用户
4. 使用专业但易懂的光学术语
5. 表面编号从 0 开始：0 = 物面 (OBJ)，最后一个 = 像面 (IMA)
6. 曲率半径单位为 mm，波长单位为 μm

注意：你只能通过提供的工具与 OpticStudio 交互，不能直接修改任何数据。
"""


# ---------------------------------------------------------------------------
#  Agent 主循环
# ---------------------------------------------------------------------------


def run_agent(client: OpenAI, model: str, toolkit: ZemaxToolkit):
    """运行 Agent 的交互循环."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    print("\n" + "=" * 60)
    print("  Zemax OpticStudio AI 助手")
    print("  输入自然语言指令与 OpticStudio 交互")
    print("  输入 'quit' 或 'exit' 退出")
    print("=" * 60 + "\n")

    while True:
        try:
            user_input = input("\033[36m你> \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break

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
                messages.pop()  # 移除失败的用户消息
                break

            choice = response.choices[0]
            assistant_msg = choice.message

            # 将助手消息加入历史
            messages.append(_message_to_dict(assistant_msg))

            # 检查是否有工具调用
            if assistant_msg.tool_calls:
                for tool_call in assistant_msg.tool_calls:
                    fn_name = tool_call.function.name
                    try:
                        fn_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        fn_args = {}

                    print(f"\033[33m  [调用工具] {fn_name}({_brief_args(fn_args)})\033[0m")
                    result = toolkit.dispatch(fn_name, fn_args)
                    print(f"\033[90m  [结果] {_truncate(result, 200)}\033[0m")

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )
                # 继续循环让 LLM 处理工具结果
                continue
            else:
                # 没有工具调用 — 输出最终回复
                reply = assistant_msg.content or ""
                print(f"\033[32m助手> {reply}\033[0m\n")
                break


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


# ---------------------------------------------------------------------------
#  入口
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Zemax OpticStudio AI Agent")
    parser.add_argument("--api-key", type=str, help="LLM API Key")
    parser.add_argument("--base-url", type=str, help="LLM API Base URL")
    parser.add_argument("--model", type=str, help="模型名称")
    parser.add_argument(
        "--zemax-mode",
        type=str,
        choices=["extension", "standalone"],
        default=None,
        help="Zemax 连接模式",
    )
    parser.add_argument("--instance", type=int, default=None, help="Extension 实例编号")
    args = parser.parse_args()

    # 加载 .env 文件
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(env_path)

    # 配置优先级: 命令行参数 > 环境变量 > 默认值
    api_key = args.api_key or os.getenv("OPENAI_API_KEY", "")
    base_url = args.base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = args.model or os.getenv("MODEL_NAME", "gpt-4")
    zemax_mode = args.zemax_mode or os.getenv("ZEMAX_MODE", "extension")
    instance = args.instance if args.instance is not None else int(os.getenv("ZEMAX_INSTANCE", "0"))

    if not api_key or api_key == "your-api-key-here":
        print("\033[31m错误: 请设置 API Key。\033[0m")
        print("方式 1: 创建 .env 文件 (参考 .env.example)")
        print("方式 2: 使用 --api-key 参数")
        print("方式 3: 设置环境变量 OPENAI_API_KEY")
        sys.exit(1)

    # 初始化 LLM 客户端
    print(f"LLM 配置: base_url={base_url}, model={model}")
    client = OpenAI(api_key=api_key, base_url=base_url)

    # 连接 Zemax
    print(f"正在连接 OpticStudio (模式: {zemax_mode}, 实例: {instance})...")
    conn = ZemaxConnection()
    try:
        conn.connect(mode=zemax_mode, instance=instance)
    except Exception as e:
        print(f"\033[31m连接 OpticStudio 失败: {e}\033[0m")
        print("\n请确保:")
        print("  1. Zemax OpticStudio 正在运行")
        print("  2. 已点击 Programming → Interactive Extension")
        sys.exit(1)

    print(f"\033[32m已连接到 OpticStudio (序列号: {conn.app.SerialCode})\033[0m")

    toolkit = ZemaxToolkit(conn)

    try:
        run_agent(client, model, toolkit)
    finally:
        conn.disconnect()
        print("已断开 OpticStudio 连接。")


if __name__ == "__main__":
    main()
