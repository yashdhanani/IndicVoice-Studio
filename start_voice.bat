@echo off
rem IndicVoice - 12-language speech-to-speech agent (CPU only)
rem Double-click to start the server and open the call page.
setlocal
cd /d "%~dp0"

if not exist ".venv313\Scripts\python.exe" (
  echo.
  echo Python 3.13 runtime not found in .venv313
  echo Follow the setup notes in requirements.txt first.
  echo.
  pause
  exit /b 1
)

if not exist ".env" (
  echo.
  echo No .env file found - the assistant cannot reply without an LLM key.
  echo Copy .env.example to .env and paste your Groq key into it.
  echo.
  pause
  exit /b 1
)

echo Starting IndicVoice on http://127.0.0.1:8000
echo First start loads 12 voices and 11 recognisers - allow ~2 minutes.
echo Press Ctrl+C to stop.
echo.

rem wait for /health instead of guessing, then open the page
start "" powershell -NoProfile -WindowStyle Hidden -Command "$u='http://127.0.0.1:8000/health'; for($i=0;$i -lt 240;$i++){ try { Invoke-WebRequest $u -UseBasicParsing -TimeoutSec 2 | Out-Null; Start-Process 'http://127.0.0.1:8000'; break } catch { Start-Sleep -Milliseconds 1500 } }"

set PYTHONIOENCODING=utf-8
".venv313\Scripts\python.exe" -m src.call_server --port 8000 --warm hi gu mr bn ta te kn ml pa or as en

pause
