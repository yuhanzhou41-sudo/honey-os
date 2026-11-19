# HoneyOS 校园同步：跑一次宿主自动采集，再把快照导入网关。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File campus-sync.ps1 -Profile major
# 注册定时（登录时 + 每 3 小时）：... -Profile major -RegisterTask
param(
    [string]$Profile = "major",
    [string]$HostExe = "C:\Users\Zyh20\Desktop\honeyos-campus-probe\CampusHost.exe",
    [string]$Gateway = "http://127.0.0.1:8642",
    [switch]$RegisterTask
)

$ErrorActionPreference = "Stop"
$logDir = Join-Path $env:LOCALAPPDATA "HoneyOS\campus"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir "sync.log"

function Write-Log([string]$Message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -Path $log -Value $line -Encoding UTF8
    Write-Output $line
}

if ($RegisterTask) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Profile $Profile"
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Hours 3)).Repetition
    Register-ScheduledTask -TaskName "HoneyOS Campus Sync ($Profile)" `
        -Action $action -Trigger $trigger -Description "HoneyOS 校园数据自动同步" `
        -User $env:USERNAME -RunLevel Limited -Force | Out-Null
    Write-Log "已注册计划任务：登录时与每 3 小时自动同步（profile=$Profile）"
    return
}

if (-not (Test-Path $HostExe)) {
    Write-Log "宿主不存在：$HostExe"
    exit 3
}

Write-Log "开始采集（profile=$Profile）"
$proc = Start-Process -FilePath $HostExe -ArgumentList "--auto", "--profile", $Profile -PassThru
$null = $proc.WaitForExit(660000)
if (-not $proc.HasExited) {
    Write-Log "宿主超时未结束，已终止"
    $proc.Kill()
    exit 4
}
Write-Log "宿主退出码 $($proc.ExitCode)"

try {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $null = Invoke-WebRequest -Uri "$Gateway/" -WebSession $session -UseBasicParsing -TimeoutSec 5
    foreach ($kind in @("exams", "timetable")) {
        $result = Invoke-RestMethod -Method Post -TimeoutSec 30 -WebSession $session `
            -Uri "$Gateway/api/campus/$kind/refresh?account=$Profile"
        $payload = $result.$kind
        Write-Log ("导入 {0}: result={1} rows={2} captured_at={3}" -f $kind, $payload.result, $payload.row_count, $payload.captured_at)
    }
} catch {
    Write-Log "导入失败：$($_.Exception.Message)"
    exit 5
}
