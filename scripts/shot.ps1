param(
    [Parameter(Mandatory = $true)][string]$Url,
    [Parameter(Mandatory = $true)][string]$Out,
    [int]$Width = 1280,
    [int]$Height = 800,
    [int]$Scale = 2,
    [int]$WaitMs = 8000
)

# 用无头 Chrome/Edge 给本地页面截图，用于里程碑存档。
# 用法：
#   .\scripts\shot.ps1 -Url http://localhost:3000 -Out docs/screenshots/w1/01-home.png
#   .\scripts\shot.ps1 -Url http://127.0.0.1:8000/docs -Out docs/screenshots/w1/02-api-docs.png -Height 1000
#
# 注意：本文件必须保存为「UTF-8 带 BOM」，否则 Windows PowerShell 5.1 会按 GBK 解析导致中文乱码报错。

$ErrorActionPreference = "Stop"

$browsers = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ }

if (-not $browsers) { throw "未找到 Chrome 或 Edge，请先安装其中之一。" }
$browser = $browsers[0]

$outFull = [System.IO.Path]::GetFullPath($Out)
$outDir = Split-Path -Parent $outFull
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
if (Test-Path $outFull) { Remove-Item $outFull -Force }

Write-Host "浏览器: $browser"
Write-Host "目标  : $Url"
Write-Host "输出  : $outFull"

$chromeArgs = @(
    "--headless=new"
    "--disable-gpu"
    "--hide-scrollbars"
    "--force-device-scale-factor=$Scale"
    "--window-size=$Width,$Height"
    "--virtual-time-budget=$WaitMs"
    "--user-data-dir=$env:TEMP\chrome-shot-profile"
    "--screenshot=$outFull"
    $Url
)

# 用 Start-Process 收走 Chrome 的输出，避免它的 stderr 提示被当成 PowerShell 异常
$logDir = Join-Path $env:TEMP "shot-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$tag = [guid]::NewGuid().ToString("N").Substring(0, 8)

$proc = Start-Process -FilePath $browser -ArgumentList $chromeArgs -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput (Join-Path $logDir "$tag.out.log") `
    -RedirectStandardError (Join-Path $logDir "$tag.err.log")

if (-not (Test-Path $outFull)) {
    $err = Get-Content (Join-Path $logDir "$tag.err.log") -Raw -ErrorAction SilentlyContinue
    throw "截图失败（退出码 $($proc.ExitCode)）：文件未生成。`n确认 $Url 可访问。`n$err"
}

Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Image]::FromFile($outFull)
$size = "{0} x {1}" -f $img.Width, $img.Height
$img.Dispose()

$kb = (Get-Item $outFull).Length / 1KB
Write-Host ("完成  : {0} px, {1:N0} KB" -f $size, $kb) -ForegroundColor Green