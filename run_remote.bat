@echo off
title BearBit Remote Control Bot (VENV)
cd /d "%~dp0"

:: 1. สร้าง venv ถ้ายังไม่มี
if not exist venv (
    echo 📦 Creating Virtual Environment...
    python -m venv venv
)

:: 2. กำหนด Path ของ Python ใน venv
set VENV_PYTHON=venv\Scripts\python.exe

:: 3. ติดตั้ง Library จาก requirements.txt
echo 📥 Checking dependencies in venv...
%VENV_PYTHON% -m pip install --upgrade pip
%VENV_PYTHON% -m pip install -r requirements.txt

:loop
echo ------------------------------------------
echo 🚀 Starting Remote Control Bot (VENV)...
echo Time: %date% %time%
echo ------------------------------------------

:: 4. รันบอท
%VENV_PYTHON% remote_control.py

echo ------------------------------------------
echo ⚠️ Bot stopped/crashed. Restarting in 5 seconds...
echo ------------------------------------------

timeout /t 5 >nul
goto loop