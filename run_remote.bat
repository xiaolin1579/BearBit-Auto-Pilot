@echo off
title BearBit Remote Control Bot
SETLOCAL EnableDelayedExpansion

:: เข้าไปยังโฟลเดอร์ที่สคริปต์ตั้งอยู่
cd /d "%~dp0"

:: 1. ตรวจสอบและเลือกคำสั่ง Python
set PYTHON_EXE=python
%PYTHON_EXE% --version >nul 2>&1
if %errorlevel% neq 0 (
    set PYTHON_EXE=py
)

:: 2. ติดตั้ง Library ที่จำเป็น (ป้องกัน ModuleNotFoundError)
echo 📥 Checking dependencies for Remote Bot...
%PYTHON_EXE% -m pip install --upgrade pip
%PYTHON_EXE% -m pip install pyTelegramBotAPI
echo ✅ Dependencies ready.

:loop
echo ------------------------------------------
echo 🚀 Starting Remote Control Bot...
echo Time: %date% %time%
echo ------------------------------------------

:: 3. รันบอทควบคุม
%PYTHON_EXE% remote_control.py

echo ------------------------------------------
echo ⚠️ Bot stopped/crashed. Restarting in 5 seconds...
echo Press Ctrl+C to stop this loop permanently.
echo ------------------------------------------

:: หน่วงเวลา 5 วินาที
timeout /t 5 >nul

goto loop