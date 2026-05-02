# scripts/status.ps1
<#
.SYNOPSIS
检查 Bilibili RAG 后端服务状态

.DESCRIPTION
输出 JSON 格式状态：{running, pid, port, started_at}
不信任 state.json.running，始终通过进程 PID 验证
#>
param(
    [string]$DataDir = "$env:USERPROFILE\.bilibili-rag"
)

$ErrorActionPreference = "Continue"
$BASE_DIR = $DataDir
$STATE_FILE = Join-Path $BASE_DIR "state.json"
$LOG_FILE = Join-Path $BASE_DIR "app.log"

function Get-StoredState {
    if (Test-Path $STATE_FILE) {
        try {
            return Get-Content $STATE_FILE -Raw | ConvertFrom-Json
        } catch { return $null }
    }
    return $null
}

function Test-ProcessAlive {
    param([int]$ProcessId)
    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        return $null -ne $proc
    } catch { return $false }
}

function Get-ActualPort {
    if (Test-Path $LOG_FILE) {
        $reader = [System.IO.File]::OpenRead($LOG_FILE)
        $lines = @()
        $buffer = New-Object byte[] 8192
        while ($reader.Position -gt 0) {
            $readLen = [Math]::Min(8192, $reader.Position)
            $reader.Position -= $readLen
            $reader.Read($buffer, 0, $readLen) | Out-Null
            $lines = ([System.Text.Encoding]::UTF8.GetString($buffer, 0, $readLen) -split "`n") + $lines
            if ($lines.Count -gt 20) { break }
        }
        $reader.Close()
        foreach ($line in $lines) {
            if ($line -match "port (\d+)") {
                return [int]$matches[1]
            }
        }
    }
    return $null
}

$state = Get-StoredState

if (-not $state -or $null -eq $state.pid) {
    @{ running = $false; pid = $null; port = $null; started_at = $null } | ConvertTo-Json -Compress
    exit 1
}

$isRunning = Test-ProcessAlive -ProcessId $state.pid
$port = if ($isRunning) { Get-ActualPort } else { $null }

@{
    running = $isRunning
    pid     = if ($isRunning) { $state.pid } else { $null }
    port    = $port
    started_at = if ($isRunning) { $state.started_at } else { $null }
} | ConvertTo-Json -Compress

exit $(if ($isRunning) { 0 } else { 1 })