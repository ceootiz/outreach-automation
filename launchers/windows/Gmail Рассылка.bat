@echo off
setlocal

set "APP_NAME=Gmail Рассылка"
set "LAUNCHER_DIR=%~dp0"
for %%I in ("%LAUNCHER_DIR%..\..") do set "PROJECT_DIR=%%~fI"
set "EXE_PATH=%PROJECT_DIR%\dist\windows\%APP_NAME%\%APP_NAME%.exe"
set "PYTHON_EXE=%PROJECT_DIR%\.venv\Scripts\python.exe"

echo Gmail Рассылка
echo Project folder: %PROJECT_DIR%
echo.

if exist "%EXE_PATH%" (
  echo Starting fresh Windows build from dist\windows...
  "%EXE_PATH%"
  goto :done
)

if not exist "%PYTHON_EXE%" (
  echo Virtual environment is missing.
  echo Run scripts\windows\setup_windows.ps1 first.
  goto :error
)

echo Built app not found. Starting dev mode...
pushd "%PROJECT_DIR%"
"%PYTHON_EXE%" app.py
set "STATUS=%ERRORLEVEL%"
popd
if not "%STATUS%"=="0" goto :error
goto :done

:error
echo.
echo Launch failed. See docs\WINDOWS_INSTALL.md for troubleshooting.
pause
exit /b 1

:done
exit /b 0
