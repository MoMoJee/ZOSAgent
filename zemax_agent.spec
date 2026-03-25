# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包规格文件 — Zemax OpticStudio AI Agent
#
# 使用方法（在项目根目录运行）:
#   .venv\Scripts\python.exe -m PyInstaller zemax_agent.spec
#
# 或直接运行构建脚本:
#   .\build.ps1

import sys
from pathlib import Path

ROOT = Path(SPECPATH)           # 项目根目录
SRC  = ROOT / "zemax_agent"    # 源码目录

# ---------------------------------------------------------------------------
#  数据文件：一并打包 .env.example、SKILL.md 等运行时需要的资源
# ---------------------------------------------------------------------------

datas = [
    # .env.example — 方便用户参考
    (str(SRC / ".env.example"), "zemax_agent"),
    # SKILL.md — AI 领域知识库（三个候选路径打包其中存在的）
    (str(ROOT / ".github" / "skills"), ".github/skills"),
]

# ---------------------------------------------------------------------------
#  隐式导入 — PyInstaller 静态分析可能遗漏的模块
# ---------------------------------------------------------------------------

hiddenimports = [
    # pywin32 COM 支持
    "win32com",
    "win32com.client",
    "win32com.client.gencache",
    "win32com.server",
    "win32com.server.policy",
    "pywintypes",
    "pythoncom",
    # MCP SDK
    "mcp",
    "mcp.server",
    "mcp.server.stdio",
    "mcp.types",
    # OpenAI
    "openai",
    "openai._base_client",
    "openai.resources",
    # 日志相关
    "concurrent_log_handler",
    "psutil",
    # 环境变量
    "dotenv",
]

# ---------------------------------------------------------------------------
#  Analysis
# ---------------------------------------------------------------------------

a = Analysis(
    [str(SRC / "main.py")],          # 入口脚本
    pathex=[str(SRC), str(ROOT)],     # 额外搜索路径
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "scipy",
        "PIL",
        "cv2",
        "test",
        "unittest",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# ---------------------------------------------------------------------------
#  单文件夹模式（推荐用于含 pywin32 / COM 的程序）
#  单文件 (--onefile) 在 pywin32 下容易出现 DLL 路径问题，故使用目录模式
# ---------------------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="zemax-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX 可能破坏 pywin32 DLL
    console=True,        # 控制台程序
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="zemax-agent",
)
