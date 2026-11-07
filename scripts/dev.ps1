# 一键启动开发环境：WSL 里的 PostgreSQL/Redis + FastAPI + Next.js
# 用法：
#   .\scripts\dev.ps1                # 启动全部，成功后自动打开浏览器
#   .\scripts\dev.ps1 -NoBrowser     # 不打开浏览器
#   .\scripts\dev.ps1 -SkipServices  # 跳过 WSL 服务（已在跑时）

param(
    [switch]$NoBrowser,
    [switch]$SkipServices
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$wslDistro = "Ubuntu-24.04"

function Test-Port([int]$Port) {
    (Test-NetConnection 127.0.0.1 -Port $Port -WarningAction SilentlyContinue).TcpTestSucceeded
}

Write-Host "== Insight Hub 开发环境 ==" -ForegroundColor Cyan
Write-Host "仓库: $root"

# ---------- 1. WSL 服务 ----------
if ($SkipServices) {
    Write-Host "[1/3] 跳过 WSL 服务检查" -ForegroundColor DarkGray
} else {
    Write-Host "[1/3] 启动 PostgreSQL / Redis ..." -ForegroundColor Yellow
    if ((Test-Port 5432) -and (Test-Port 6379)) {
        Write-Host "      已在运行，跳过" -ForegroundColor DarkGray
    } else {
        wsl -d $wslDistro -u root -- /usr/local/bin/start-services.sh | ForEach-Object { "      $_" }
    }
}

# ---------- 2. 后端 ----------
Write-Host "[2/3] 启动 FastAPI ..." -ForegroundColor Yellow
if (Test-Port 8000) {
    Write-Host "      8000 已被占用，跳过（如果显示异常，先关掉占用窗口）" -ForegroundColor DarkGray
} else {
    $apiPy = Join-Path $root "apps\api\.venv\Scripts\python.exe"
    if (-not (Test-Path $apiPy)) {
        throw "找不到 $apiPy，先在 apps\api 下执行：uv venv --python 3.12 .venv && uv pip install -r requirements.txt"
    }
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-NoProfile",
        "-Command", "`$host.UI.RawUI.WindowTitle='Insight Hub API'; cd '$root\apps\api'; .\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000"
    )
}

# ---------- 3. 前端 ----------
Write-Host "[3/3] 启动 Next.js ..." -ForegroundColor Yellow
if (Test-Port 3000) {
    Write-Host "      3000 已被占用，跳过" -ForegroundColor DarkGray
} else {
    Start-Process powershell -ArgumentList @(
        "-NoExit", "-NoProfile",
        "-Command", "`$host.UI.RawUI.WindowTitle='Insight Hub Web'; cd '$root\apps\web'; npm.cmd run dev"
    )
}

# ---------- 4. 等就绪 ----------
Write-Host "等待服务就绪 ..." -ForegroundColor Yellow
$deadline = (Get-Date).AddSeconds(90)
$apiOk = $false
$webOk = $false
while ((Get-Date) -lt $deadline) {
    if (-not $apiOk) {
        try {
            $h = Invoke-WebRequest "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 3
            $apiOk = ($h.StatusCode -eq 200)
        } catch { }
    }
    if (-not $webOk) {
        try {
            $w = Invoke-WebRequest "http://localhost:3000" -UseBasicParsing -TimeoutSec 3
            $webOk = ($w.StatusCode -eq 200)
        } catch { }
    }
    if ($apiOk -and $webOk) { break }
    Start-Sleep -Milliseconds 1500
    Write-Host "." -NoNewline -ForegroundColor DarkGray
}
Write-Host ""

# ---------- 5. 汇报 ----------
Write-Host ""
if ($apiOk) {
    $health = (Invoke-WebRequest "http://127.0.0.1:8000/api/health" -UseBasicParsing -TimeoutSec 5).Content
    Write-Host "API : http://127.0.0.1:8000/api/health" -ForegroundColor Green
    Write-Host "      $health" -ForegroundColor DarkGray
} else {
    Write-Host "API : 未就绪，看那个标题为 'Insight Hub API' 的窗口报了什么错" -ForegroundColor Red
}

if ($webOk) {
    Write-Host "Web : http://localhost:3000" -ForegroundColor Green
} else {
    Write-Host "Web : 未就绪，看 'Insight Hub Web' 窗口" -ForegroundColor Red
}

if (-not $NoBrowser -and $webOk) {
    Start-Process "http://localhost:3000"
}

Write-Host ""
Write-Host "停止：关掉那两个 PowerShell 窗口即可（数据库服务会继续在后台跑）" -ForegroundColor DarkGray