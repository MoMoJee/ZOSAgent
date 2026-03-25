# build.ps1 — Zemax OpticStudio AI Agent 打包脚本
# 在项目根目录运行: .\build.ps1

$ErrorActionPreference = "Stop"

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv     = Join-Path $Root ".venv"
$Python   = Join-Path $Venv "Scripts\python.exe"
$DistDir  = Join-Path $Root "dist\zemax-agent"
$SpecFile = Join-Path $Root "zemax_agent.spec"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Zemax OpticStudio AI Agent — PyInstaller 打包" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# 检查 venv
if (-not (Test-Path $Python)) {
    Write-Host "[错误] 未找到虚拟环境: $Python" -ForegroundColor Red
    Write-Host "请先创建 venv：python -m venv .venv && .venv\Scripts\pip install -r zemax_agent\requirements.txt"
    exit 1
}

# 确保 PyInstaller 已安装
Write-Host "[1/3] 检查 PyInstaller..." -ForegroundColor Yellow
& $Python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  安装 PyInstaller..."
    & $Python -m pip install pyinstaller --quiet
}
Write-Host "  OK" -ForegroundColor Green

# 清理旧构建
Write-Host "[2/3] 清理旧输出..." -ForegroundColor Yellow
if (Test-Path (Join-Path $Root "build")) { Remove-Item -Recurse -Force (Join-Path $Root "build") }
if (Test-Path (Join-Path $Root "dist"))  { Remove-Item -Recurse -Force (Join-Path $Root "dist")  }
Write-Host "  OK" -ForegroundColor Green

# 执行打包
Write-Host "[3/3] 运行 PyInstaller..." -ForegroundColor Yellow
Set-Location $Root
& $Python -m PyInstaller $SpecFile --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[失败] PyInstaller 打包出错，请查看上方输出。" -ForegroundColor Red
    exit 1
}

# 打包后处理：复制 .env.example 到输出目录
$EnvExample = Join-Path $Root "zemax_agent\.env.example"
if (Test-Path $EnvExample) {
    Copy-Item $EnvExample (Join-Path $DistDir "zemax_agent\.env.example") -Force
}

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  打包完成！输出目录: dist\zemax-agent\"         -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "使用方法:" -ForegroundColor Cyan
Write-Host "  1. 进入 dist\zemax-agent\"
Write-Host "  2. 复制 zemax_agent\.env.example 为 zemax_agent\.env 并填入 API Key"
Write-Host "  3. 运行 zemax-agent.exe --setup   （首次配置向导）"
Write-Host "  4. 运行 zemax-agent.exe           （启动 CLI AI 助手）"
Write-Host "  5. 运行 zemax-agent.exe --mcp     （启动 MCP 服务器）"
