@echo off
setlocal enabledelayedexpansion

if "%COMFYUI_HOME%"=="" (
  echo [ERROR] COMFYUI_HOME is not set. Point it to your ComfyUI folder (contains main.py).
  exit /b 1
)

set "COMFY_REGISTRY=%TEMP%\comfy_registry_%RANDOM%.jsonl"

echo === START ===
for /f "usebackq delims=" %%U in (`comfy-remote start --host 127.0.0.1 --port 0 --registry "%COMFY_REGISTRY%"`) do set "BASE_URL=%%U"
if "%BASE_URL%"=="" (
  echo [ERROR] start did not return a URL
  exit /b 2
)
echo started: %BASE_URL%

echo.
echo === LIST ===
comfy-remote list --registry "%COMFY_REGISTRY%"

echo.
echo === ATTACH ===
comfy-remote attach --url "%BASE_URL%" --registry "%COMFY_REGISTRY%" --json

echo.
echo === CONNECT ===
comfy-remote connect --url "%BASE_URL%" --registry "%COMFY_REGISTRY%" --timeout 5

echo.
echo === STOP ===
comfy-remote stop --url "%BASE_URL%" --registry "%COMFY_REGISTRY%"

echo.
echo Done.
endlocal
