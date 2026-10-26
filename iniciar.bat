@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 server.py
  goto :eof
)
python server.py
if errorlevel 1 (
  echo.
  echo Nao foi possivel iniciar. Instale Python 3.10 ou superior e tente de novo.
  pause
)
