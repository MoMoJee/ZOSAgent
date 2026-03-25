# Zemax OpticStudio AI Agent

用自然语言驱动 Zemax OpticStudio 进行光学设计与优化。

支持两种使用方式：

| 模式 | 说明 |
|------|------|
| **CLI AI 助手** | 在终端直接对话，AI 自动调用 OpticStudio 工具完成设计任务 |
| **MCP 服务器** | 将 OpticStudio 工具暴露为 MCP 协议服务，供 VS Code Copilot / Claude Desktop 调用 |

---

## 目录

- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [CLI AI 助手](#cli-ai-助手)
- [MCP 服务器（VS Code / Claude Desktop）](#mcp-服务器vs-code--claude-desktop)
- [.env 配置详解](#env-配置详解)
- [可用工具列表](#可用工具列表)
- [日志系统](#日志系统)
- [打包为可执行文件](#打包为可执行文件)
- [二次开发指南](#二次开发指南)
- [常见问题排查](#常见问题排查)

---

## 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | 3.10 + | 推荐 3.12 |
| Zemax OpticStudio | 2018 + | 需要 ZOS-API 许可证 |
| 操作系统 | Windows 10/11 | ZOS-API 仅支持 Windows |
| pywin32 | ≥ 306 | COM 接口驱动 |

---

## 快速开始

### 1. 克隆 / 下载项目

```powershell
git clone <repo-url>
cd "ZOS-API Projects\PythonZOSConnection"
```

### 2. 创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r zemax_agent\requirements.txt
```

### 3. 运行配置向导

```powershell
cd zemax_agent
python main.py --setup
```

按提示填入 API Key、Base URL、模型名称和 Zemax 连接模式即可。配置保存在 `zemax_agent/.env`。

### 4. 启动 OpticStudio 并激活 Interactive Extension

1. 打开 Zemax OpticStudio
2. 点击菜单 **Programming → Interactive Extension**

### 5. 启动 AI 助手

```powershell
python main.py
```

---

## CLI AI 助手

```powershell
# 基本启动
python main.py

# 临时指定模型（不修改 .env）
python main.py --model gpt-4o

# 清理 COM 缓存后启动（遇到属性映射错误时使用）
python main.py --clear-cache
```

### 内置命令

| 命令 | 说明 |
|------|------|
| `help` | 显示常用自然语言指令示例 |
| `reconnect` | 手动重连 OpticStudio |
| `clear` | 清空对话历史（不影响 OpticStudio 中已有的系统） |
| `quit` / `exit` / `q` | 退出 |

### 自然语言示例

```
你> 显示当前光学系统状态
你> 新建一个双胶合消色差透镜，f=100mm，入瞳20mm
你> 设置 F/d/C 三色光波长
你> 把所有曲率半径设为变量，运行 DLS 优化
你> 查看系统焦距和总长
你> 打开 2D 布局图
你> 保存为 C:/Zemax/Samples/doublet.zmx
```

---

## MCP 服务器（VS Code / Claude Desktop）

### 启动方式

```powershell
# 通过 main.py 启动（推荐）
python zemax_agent\main.py --mcp

# 直接启动 mcp_server.py
python zemax_agent\mcp_server.py
```

### VS Code 配置

在 `.vscode/mcp.json` 中添加：

```json
{
  "servers": {
    "zemax-opticstudio": {
      "type": "stdio",
      "command": "C:\\path\\to\\project\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\path\\to\\project\\zemax_agent\\main.py",
        "--mcp"
      ]
    }
  }
}
```

### Claude Desktop 配置

在 `%APPDATA%\Claude\claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "zemax-opticstudio": {
      "command": "C:\\path\\to\\project\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\path\\to\\project\\zemax_agent\\main.py",
        "--mcp"
      ]
    }
  }
}
```

参考 `claude_desktop_config_example.json` 文件。

---

## .env 配置详解

文件位置：`zemax_agent/.env`（首次运行 `python main.py --setup` 自动生成）

```dotenv
# ── LLM API ──────────────────────────────────────────────────
# 支持任何 OpenAI 兼容接口
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1   # DeepSeek（推荐，性价比高）
# OPENAI_BASE_URL=https://api.openai.com/v1   # 官方 OpenAI
# OPENAI_BASE_URL=http://localhost:11434/v1   # 本地 Ollama
MODEL_NAME=deepseek-chat                       # 模型名

# ── Zemax 连接 ────────────────────────────────────────────────
ZEMAX_MODE=extension      # extension: 连接到已运行的 OpticStudio（推荐）
                          # standalone: Python 自动启动 OpticStudio 新实例
ZEMAX_INSTANCE=0          # Interactive Extension 实例编号（通常为 0）
```

### 常用 API 服务配置

| 服务 | Base URL | 推荐模型 |
|------|----------|----------|
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 阿里云百炼 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-max` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| 本地 Ollama | `http://localhost:11434/v1` | `llama3.1` |

---

## 可用工具列表

MCP 服务器和 CLI 助手共享以下 24 个工具，外加 1 个连接管理工具：

### 系统信息
| 工具 | 说明 |
|------|------|
| `get_system_info` | 获取当前系统概览（表面/光圈/视场/波长） |
| `get_first_order_data` | 获取一阶光学参数（EFFL / TOTR / BFL 等） |

### 表面操作
| 工具 | 说明 |
|------|------|
| `insert_surface` | 在指定位置插入新表面 |
| `edit_surface` | 修改表面参数（曲率/厚度/材料/半口径/圆锥系数） |
| `remove_surface` | 删除指定表面 |
| `set_surface_type` | 设置表面类型（Standard / EvenAsphere 等） |

### 系统参数
| 工具 | 说明 |
|------|------|
| `set_aperture` | 设置入瞳直径 / F/# 等光圈类型 |
| `set_fields` | 设置视场点 |
| `set_wavelengths` | 设置波长（手动列表，支持权重） |

### 评价函数
| 工具 | 说明 |
|------|------|
| `set_default_merit_function` | 用向导生成默认评价函数（含厚度约束） |
| `add_operand` | 手动添加操作数（EFFL / BFL / TOTR 等） |
| `get_merit_function` | 获取评价函数当前值 |
| `get_operands` | 查看所有操作数的目标值和当前值 |
| `remove_operands` | 删除指定行的操作数 |

### 优化
| 工具 | 说明 |
|------|------|
| `make_variable` | 将表面参数设为变量或固定 |
| `run_optimization` | 运行局部优化（DLS / OD）|
| `quick_focus` | 快速对焦（移动最后一个气隙） |

### 玻璃库
| 工具 | 说明 |
|------|------|
| `get_glass_catalogs` | 查询已加载和可用的玻璃目录 |
| `set_glass_catalogs` | 添加或移除玻璃目录 |

### 文件
| 工具 | 说明 |
|------|------|
| `new_file` | 新建空白系统 |
| `open_file` | 打开 .zmx 文件 |
| `save_file` | 保存或另存为 |

### GUI 布局
| 工具 | 说明 |
|------|------|
| `open_layout` | 打开 2D 或 3D 布局图窗口 |
| `update_ui` | 强制刷新 OpticStudio GUI |

### 连接管理
| 工具 | 说明 |
|------|------|
| `reconnect_zemax` | 重新连接到 OpticStudio（仅 MCP 模式） |

> **自动 UI 刷新**：每次执行写操作工具（如 `edit_surface`、`run_optimization`）后，程序会自动调用 `UpdateStatus()` 刷新 LDE 和已打开的分析窗口，无需手动调用 `update_ui`。

---

## 日志系统

日志文件位于项目根目录的 `logs/ZOS-AI.log`，采用滚动策略（单文件 2.5 MB，保留 10 个备份）。

```
logs/
├── ZOS-AI.log       ← 当前日志
├── ZOS-AI.log.1     ← 最近一个备份
└── ...
```

日志格式：
```
2026-03-25 14:00:01 | INFO     | zemax_agent/main.py | main:123 | OpticStudio 连接成功，序列号: 12345
```

控制台仅输出 INFO 及以上级别；文件记录 DEBUG 及以上级别（含完整函数名和行号）。

---

## 打包为可执行文件

将程序打包为 Windows 可执行文件（`.exe`），便于在没有安装 Python 的机器上运行。

### 方式一：使用构建脚本（推荐）

```powershell
.\build.ps1
```

### 方式二：手动运行 PyInstaller

```powershell
.venv\Scripts\python.exe -m PyInstaller zemax_agent.spec --noconfirm
```

### 输出位置

```
dist\
└── zemax-agent\
    ├── zemax-agent.exe          ← 主程序
    ├── zemax_agent\
    │   └── .env.example         ← 配置模板
    └── .github\skills\...       ← 领域知识库
```

### 分发给用户

1. 将 `dist\zemax-agent\` 整个目录复制给用户
2. 用户进入目录，运行首次配置：
   ```
   zemax-agent.exe --setup
   ```
3. 填写 API Key 后即可使用：
   ```
   zemax-agent.exe           # CLI AI 助手
   zemax-agent.exe --mcp     # MCP 服务器
   ```

> **注意**：目标机器需要安装与打包版本一致的 Zemax OpticStudio 和 pywin32（win32com DLL），exe 本身不含 COM 类型库。

---

## 二次开发指南

### 项目结构

```
PythonZOSConnection/
├── zemax_agent/
│   ├── main.py             ← 统一入口（CLI + MCP 启动器）
│   ├── mcp_server.py       ← MCP stdio 服务器实现
│   ├── tools.py            ← 24个工具定义 + ZemaxToolkit 实现
│   ├── zemax_connection.py ← COM 连接管理（含属性探测和自动重连）
│   ├── logger.py           ← 全局日志器（单例，文件+控制台）
│   ├── requirements.txt    ← Python 依赖
│   ├── .env                ← 本地配置（不提交 git）
│   └── .env.example        ← 配置模板
├── .github/skills/
│   └── zemax-optical-design/
│       └── SKILL.md        ← AI 领域知识库（注入系统提示词）
├── zemax_agent.spec        ← PyInstaller 打包规格
├── build.ps1               ← 一键打包脚本
└── README.md
```

### 添加新工具

**步骤 1**：在 `tools.py` 的 `TOOL_DEFINITIONS` 列表末尾添加工具声明：

```python
{
    "type": "function",
    "function": {
        "name": "my_new_tool",
        "description": "工具功能描述（给 AI 看的）",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "参数说明"},
            },
            "required": ["param1"],
        },
    },
},
```

**步骤 2**：在 `ZemaxToolkit` 类中实现同名方法：

```python
def my_new_tool(self, param1: str) -> str:
    """工具实现."""
    system = self.conn.system
    # 调用 ZOS-API ...
    result = {"ok": True, "data": param1}
    return json.dumps(result, ensure_ascii=False)
```

**步骤 3**（可选）：如果是只读工具（不修改系统状态），将工具名加入 `_READ_ONLY_TOOLS` 集合，避免触发不必要的 UI 刷新：

```python
_READ_ONLY_TOOLS: frozenset[str] = frozenset({
    ...,
    "my_new_tool",
})
```

**步骤 4**：在 `SKILL.md` 中补充该工具的使用说明（可选但推荐）。

### 更新领域知识

编辑 `.github/skills/zemax-optical-design/SKILL.md`，内容会在 CLI Agent 启动时自动加载并注入到 AI 系统提示词。YAML frontmatter（`---` 括起的部分）会被自动去除。

### 修改 AI 行为

编辑 `main.py` 中的 `_SYSTEM_BASE` 字符串可调整 AI 的基础指令和行为规范。

### COM 属性探测机制

针对不同版本 OpticStudio COM 接口属性名不一致的问题，`ZemaxConnection._probe_interfaces()` 在连接时自动探测真实属性名并缓存到 `conn._prop_cache`。如遇新版本属性名变化，可在 `_detect_wavelength_props()` 和 `_detect_field_props()` 中扩展候选名称列表。

---

## 常见问题排查

### 连接失败：无法连接到 OpticStudio

1. 确认 Zemax OpticStudio 正在运行
2. 确认已点击 **Programming → Interactive Extension**（每次重启 OpticStudio 都需要重新点击）
3. 尝试清理 COM 缓存：`python main.py --clear-cache`

### AttributeError / COM 类型错误

```powershell
python main.py --clear-cache
```

这会删除 `%TEMP%\gen_py\` 中的旧 ZOS-API 包装器，让 pywin32 重新生成。

### LLM 请求失败 / API Key 无效

- 检查 `.env` 中的 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL` 是否正确
- 如使用代理或国内服务，确认 `OPENAI_BASE_URL` 与提供商文档一致
- 重新运行向导：`python main.py --setup`

### 优化后 GUI 没有刷新

- 检查 OpticStudio 中是否已打开 2D/3D 布局窗口（`open_layout` 工具）
- 手动触发：对话中输入"刷新界面"，AI 会调用 `update_ui` 工具

### 波长/视场设置后数量不对

- **不要使用 `preset` 参数**，直接手动传入 `wavelengths` 列表（旧版 ZOS-API preset 不可靠）
- 设置后用 `get_system_info` 确认

### PyInstaller 打包后运行报错

- 确保目标机器已安装相同版本的 Zemax OpticStudio
- COM DLL（pythoncom / pywintypes）需与目标 Python 架构（64-bit）匹配
- 首次运行在目标机器上执行一次 `zemax-agent.exe --clear-cache`

---

## License

本项目仅供学习和个人使用。Zemax OpticStudio 及 ZOS-API 版权归 Zemax LLC / Ansys Inc. 所有。
