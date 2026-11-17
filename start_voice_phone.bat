@echo off
rem IndicVoice - serve over HTTPS so phones on your Wi-Fi can use the microphone.
rem Browsers only grant mic access on a secure origin, so http://<ip> will not work.
rem Set INDICVOICE_TOKEN in .env first, otherwise anyone on the network can use your key.
setlocal
cd /d "%~dp0"

if not exist ".venv313\Scripts\python.exe" (
  echo Python 3.13 runtime not found in .venv313 - see requirements.txt
  pause & exit /b 1
)

set PYTHONIOENCODING=utf-8
echo Starting IndicVoice over HTTPS on port 8443 (self-signed certificate).
echo Phones: open https://^<this-pc-ip^>:8443/?token=^<your-token^> and accept the warning.
echo.

".venv313\Scripts\python.exe" -m src.call_server --host 0.0.0.0 --port 8443 --tls --warm hi gu mr bn ta te kn ml pa or as en

pause
