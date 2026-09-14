@echo off
REM ============================================================
REM  RSS-GPT scorer - run locally, then push the result.
REM  Usage: double-click this file. No arguments needed.
REM  It will pick the newest intent-marks*.jsonl from your Downloads.
REM  (Kept ASCII-only: Chinese in .bat files breaks under GBK cmd.)
REM ============================================================
chcp 65001 >nul
setlocal

set PY=D:\anaconda\python.exe
set REPO=RSS-GPT

echo.
echo === 1/4  run scorer ===
cd /d "%~dp0"
"%PY%" score_local.py %*
if errorlevel 1 (
  echo.
  echo [X] scorer failed. Nothing was pushed.
  pause
  exit /b 1
)

echo.
echo === 2/4  pull latest ===
cd /d "%~dp0.."
git pull --rebase --autostash origin main
if errorlevel 1 (
  echo.
  echo [X] git pull failed (network or conflict). Nothing was pushed.
  pause
  exit /b 1
)

echo.
echo === 3/4  commit ===
git add -A
for /f "tokens=1-4 delims=/ " %%a in ("%date% %time%") do set NOW=%%a %%b %%c
git commit -m "Auto Score at %NOW%" || echo (nothing changed)

echo.
echo === 4/4  push ===
git push origin main
if errorlevel 1 (
  echo.
  echo [!] push failed. Run this file again in a minute.
  pause
  exit /b 1
)

echo.
echo [OK] done. Site updates in 1-2 minutes:
echo      https://spike29796.github.io/RSS-GPT/
echo.
pause
