#!/bin/bash
# เข้าไปยังโฟลเดอร์ที่สคริปต์นี้ตั้งอยู่
cd "$(dirname "$0")"

# 1. สร้าง venv ถ้ายังไม่มี
if [ ! -d "venv" ]; then
    echo "📦 Creating Virtual Environment..."
    python3 -m venv venv
fi

# 2. Activate และติดตั้ง requirements
source venv/bin/activate
echo "📥 Installing/Updating dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

while true
do
    echo "------------------------------------------"
    echo "🚀 Starting Remote Control Bot (VENV)..."
    echo "Time: $(date)"
    echo "------------------------------------------"
    
    # รันบอทโดยใช้ python ใน venv
    python3 remote_control.py
    
    echo "------------------------------------------"
    echo "⚠️ Bot stopped/crashed. Restarting in 5 seconds..."
    echo "------------------------------------------"
    
    sleep 5
done