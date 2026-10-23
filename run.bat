@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [1/2] Dang tao moi truong Python .venv ...
  python -m venv .venv
  if errorlevel 1 goto :error
  echo [2/2] Dang cai thu vien ...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto :error
)

echo Dang khoi dong bo nen...
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :error
goto :eof

:error
echo.
echo Co loi xay ra. Xem thong bao phia tren.
pause
exit /b 1
