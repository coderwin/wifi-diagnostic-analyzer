@echo off
chcp 65001 > nul
echo ========================================================
echo   Wi-Fi Sentinel 백그라운드 모니터링 데몬 실행기
echo ========================================================

set SCRIPT_DIR=%~dp0..
cd /d "%SCRIPT_DIR%"

if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
) else (
    set PYTHON_EXE=python
)

echo 실행 경로: %SCRIPT_DIR%
echo 파이썬: %PYTHON_EXE%
echo.
echo 상시 모니터링을 시작합니다. (종료: Ctrl + C)
"%PYTHON_EXE%" src/main.py monitor
pause
