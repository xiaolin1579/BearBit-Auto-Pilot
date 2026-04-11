#!/bin/bash
# เข้าไปยังโฟลเดอร์ที่สคริปต์นี้ตั้งอยู่
cd "$(dirname "$0")"

while true
do
    echo "------------------------------------------"
    echo "Starting Remote Control Bot..."
    echo "Time: $(date)"
    echo "------------------------------------------"
    
    # รันบอทควบคุม
    python3 remote_control.py
    
    echo "------------------------------------------"
    echo "Bot stopped/crashed. Restarting in 5 seconds..."
    echo "Press Ctrl+C to stop this loop permanently."
    echo "------------------------------------------"
    
    sleep 5
done