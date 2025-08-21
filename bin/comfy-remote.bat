@echo off
setlocal
REM comfy-remote.bat — runs the Python CLI (comfyui_remote.cli.main) with repo/src on PYTHONPATH.

REM 1) Locate repo root and src/
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "ROOT=%%~fI"
set "SRC_DIR=%ROOT%\src"
if exist "%SRC_DIR%\comfyui_remote\cli\main.py" (
  set "PYTHONPATH=%SRC_DIR%;%PYTHONPATH%"
) else (
  echo [ERROR] Could not find src\comfyui_remote\cli\main.py near %SCRIPT_DIR%
  echo         Expected: %SRC_DIR%
  exit /b 2
)

REM 2) If you want to pin the interpreter, set COMFY_REMOTE_PY to a python.exe path
if defined COMFY_REMOTE_PY (
  if exist "%COMFY_REMOTE_PY%" (
    "%COMFY_REMOTE_PY%" -m comfyui_remote.cli.main %*
    exit /b %ERRORLEVEL%
  ) else (
    echo [WARN] COMFY_REMOTE_PY is set but not found: %COMFY_REMOTE_PY%
  )
)

REM 3) Prefer Windows 'py' launcher (Python 3.x), fallback to 'python'
where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 -m comfyui_remote.cli.main %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python -m comfyui_remote.cli.main %*
  exit /b %ERRORLEVEL%
)

echo [ERROR] No Python found on PATH. Install Python 3.10+ or set COMFY_REMOTE_PY to your python.exe
exit /b 1
endlocal
