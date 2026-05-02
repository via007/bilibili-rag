# scripts/start.ps1
<#
.SYNOPSIS
启动 Bilibili RAG 后端服务

.PARAMETER Port
默认 8000
#>

param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR
$LOG_FILE = Join-Path $PROJECT_ROOT "app.log"

function Test-PortOpen {
    param([int]$Port)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect("127.0.0.1", $Port)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

# 检查端口是否已被占用
if (Test-PortOpen -Port $Port) {
    Write-Host "[ERROR] Port $Port is already in use" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Starting service on port $Port..." -ForegroundColor Cyan
Write-Host "[INFO] Working directory: $PROJECT_ROOT" -ForegroundColor Cyan

# 激活 conda 环境并启动服务
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "powershell"
$psi.Arguments = "-NoProfile -Command `"Set-Location '$PROJECT_ROOT'; conda activate bilibili-rag 2`$null; if (`$LASTEXITCODE -ne 0) { python -m uvicorn app.main:app --host 127.0.0.1 --port $Port } else { uvicorn app.main:app --host 127.0.0.1 --port $Port }`""
$psi.WorkingDirectory = $PROJECT_ROOT
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true

$env:PYTHONIOENCODING = "utf-8"
$proc = [System.Diagnostics.Process]::Start($psi)

# 等待服务就绪（最多 30 秒）
$timeout = 30
$started = $false
for ($i = 0; $i -lt $timeout * 2; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-PortOpen -Port $Port) {
        $started = $true
        break
    }
}

if (-not $started) {
    Write-Host "[ERROR] Service failed to start within ${timeout}s" -ForegroundColor Red
    Write-Host "===== Log =====" -ForegroundColor Yellow
    if (Test-Path $LOG_FILE) {
        Get-Content $LOG_FILE -Tail 30
    }
    exit 1
}

Write-Host "[OK]   Service running at http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host $Port

exit 0