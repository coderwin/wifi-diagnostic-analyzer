# Windows 작업 스케줄러에 Wi-Fi Sentinel 모니터링 데몬 등록 스크립트
# 관리자 권한 PowerShell에서 실행하세요.

$TaskName = "WiFiSentinelMonitor"
$ScriptDir = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    $PythonExe = (Get-Command python.exe).Source
}

$Arguments = "src/main.py monitor"

Write-Host "Wi-Fi Sentinel 작업 스케줄러 등록 중..." -ForegroundColor Cyan
Write-Host "작업 이름: $TaskName"
Write-Host "실행 파일: $PythonExe"
Write-Host "작업 디렉터리: $ScriptDir"

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument $Arguments -WorkingDirectory $ScriptDir
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Days 365)

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Wi-Fi 장애 진단 및 패턴 분석 상시 모니터링 데몬"
    Write-Host "✔ Windows 작업 스케줄러 등록 완료!" -ForegroundColor Green
    Write-Host "컴퓨터 로그인 시 백그라운드에서 자동 구동됩니다."
} catch {
    Write-Error "등록 실패: 관리자 권한으로 실행했는지 확인하세요. ($_)"
}
