# scripts/stop.ps1
<#
.SYNOPSIS
停止 Bilibili RAG 后端服务

.PARAMETER Port
服务端口，默认 8000

.PARAMETER Force
跳过优雅终止，直接强制 kill

.PARAMETER Timeout
优雅终止等待秒数，默认 10
#>
param(
    [int]$Port = 8000,
    [switch]$Force,
    [int]$Timeout = 10
)

$ErrorActionPreference = "Continue"

# 查找占用端口的进程
$conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $conn) {
    Write-Host "[OK]   Port $Port is not in use, service is not running" -ForegroundColor Green
    exit 0
}

$processId = $conn.OwningProcess
Write-Host "[INFO] Found process $processId on port $Port" -ForegroundColor Cyan

# 尝试优雅终止
if (-not $Force) {
    try {
        $proc = Get-Process -Id $processId -ErrorAction Stop
        $proc.CloseMainWindow() | Out-Null
        $exited = $proc.WaitForExit(1000 * $Timeout)
        if ($exited) {
            Write-Host "[OK]   Service stopped gracefully" -ForegroundColor Green
            exit 0
        }
        Write-Host "[WARN] Graceful stop timed out, force killing..." -ForegroundColor Yellow
    } catch {
        Write-Host "[WARN] Could not send close signal: $_" -ForegroundColor Yellow
    }
}

# 强制终止
try {
    Stop-Process -Id $processId -Force -ErrorAction Stop
    Write-Host "[OK]   Process forcefully stopped" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to stop process: $_" -ForegroundColor Red
    exit 1
}

exit 0