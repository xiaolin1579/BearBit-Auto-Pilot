import telebot
from telebot import types
import time
import json
import os
import sys
import subprocess

# --- SETUP PATH ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
LOG_PATH = os.path.join(BASE_DIR, 'bot.log')

def load_config():
    # โครงสร้างพื้นฐานกรณีไม่มีไฟล์
    default_config = {
        "BEARBIT": {"user": "", "pass": ""},
        "TELEGRAM_CONFIG": {
            "remote_enable": True, 
            "remote_bot_token": "YOUR_TOKEN", 
            "chat_id": "YOUR_ID"
        },
        "SETTING": {"MIN_SIZE_GB": 1.0, "MAX_SIZE_GB": 500.0},
        "NODES": []
    }
    
    if not os.path.exists(CONFIG_PATH):
        print(f"⚠️ ไม่พบ {CONFIG_PATH} -> กำลังสร้างไฟล์เริ่มต้น...")
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        return default_config
        
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

# --- INITIALIZE REMOTE BOT ---
cfg = load_config()
TELE_CFG = cfg.get('TELEGRAM_CONFIG', {})

if not TELE_CFG.get('remote_enable', False):
    print("⚠️ Remote Bot ถูกปิดใช้งานอยู่ใน config.json")
    sys.exit(0)

TOKEN = TELE_CFG.get('remote_bot_token')
if not TOKEN:
    print("❌ Error: ไม่พบ remote_bot_token ใน config.json")
    sys.exit(1)

try:
    ADMIN_ID = int(TELE_CFG.get('chat_id'))
except (ValueError, TypeError):
    print("❌ Error: chat_id ไม่ถูกต้อง")
    sys.exit(1)

bot = telebot.TeleBot(TOKEN)

# --- KEYBOARD MENUS ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add('📊 Status Check', '⚙️ Config Settings')
    markup.add('📄 View Last Log', '📁 Download Full Log')
    markup.add('🎮 Bot Controls')
    return markup

def settings_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add('📏 Set Min Size', '📐 Set Max Size', '♻️ Toggle Freeload', '⬅️ Back to Main')
    return markup

def controls_menu():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add('🚀 Start Main Bot', '🚫 Stop Main Bot', '🔄 Restart Main Bot', '🔄 Restart Remote', '⬅️ Back to Main')
    return markup

def is_process_running(name):
    try:
        subprocess.check_output(["pgrep", "-f", name])
        return True
    except subprocess.CalledProcessError:
        return False

@bot.message_handler(commands=['start'])
def welcome(message):
    if message.chat.id == ADMIN_ID:
        bot.reply_to(message, "🕹️ BearBit Remote Control (Online)", reply_markup=main_menu())

@bot.message_handler(func=lambda message: True)
def handle_msg(message):
    if message.chat.id != ADMIN_ID: return

    # --- เมนูหลัก ---
    if message.text == '⚙️ Config Settings':
        bot.send_message(message.chat.id, "🛠️ ตั้งค่าการกรองไฟล์", reply_markup=settings_menu())
    
    elif message.text == '🎮 Bot Controls':
        bot.send_message(message.chat.id, "🕹️ ควบคุมระบบบอท", reply_markup=controls_menu())
    
    elif message.text == '⬅️ Back to Main':
        bot.send_message(message.chat.id, "🏠 กลับหน้าหลัก", reply_markup=main_menu())

    # --- ตรวจสอบสถานะ ---
    elif message.text == '📊 Status Check':
        cfg_now = load_config()
        SET = cfg_now.get('SETTING', {})
        main_running = is_process_running("python3 main.py")
        status = (f"📍 **System Status**\n"
                  f"• Main Bot: `{'🟢 Online' if main_running else '🔴 Offline'}`\n"
                  f"• Min-Max: `{SET.get('MIN_SIZE_GB')} - {SET.get('MAX_SIZE_GB')} GB`\n"
                  f"• Freeload Only: `{'✅ Yes' if SET.get('FREELOAD_ENABLE') else '❌ No'}`")
        bot.send_message(message.chat.id, status, parse_mode='Markdown')

    # --- จัดการ Log ---
    elif message.text == '📄 View Last Log':
        if os.path.exists(LOG_PATH):
            logs = subprocess.check_output(["tail", "-n", "20", LOG_PATH]).decode('utf-8')
            bot.send_message(message.chat.id, f"📄 **Last 20 Lines:**\n```\n{logs}\n```", parse_mode='Markdown')
        else:
            bot.send_message(message.chat.id, "❌ ไม่พบไฟล์ Log")

    elif message.text == '📁 Download Full Log':
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, 'rb') as f:
                bot.send_document(message.chat.id, f, caption="📄 Full Log")
        else:
            bot.send_message(message.chat.id, "❌ ไม่พบไฟล์ Log")

    # --- ฟังก์ชันแก้ไข Config (แบบ Interactive) ---
    elif message.text == '📏 Set Min Size':
        msg = bot.send_message(message.chat.id, "🔢 ส่งค่า Min Size (GB) ที่ต้องการ (เช่น 15):")
        bot.register_next_step_handler(msg, update_min_size)

    elif message.text == '📐 Set Max Size':
        msg = bot.send_message(message.chat.id, "🔢 ส่งค่า Max Size (GB) ที่ต้องการ (เช่น 200):")
        bot.register_next_step_handler(msg, update_max_size)

    elif message.text == '♻️ Toggle Freeload':
        c = load_config()
        current = c['SETTING'].get('FREELOAD_ENABLE', True)
        c['SETTING']['FREELOAD_ENABLE'] = not current
        save_config(c)
        bot.send_message(message.chat.id, f"✅ เปลี่ยน Freeload เป็น: `{'On' if not current else 'Off'}`", parse_mode='Markdown')

    # --- ควบคุมบอท ---
    elif message.text == '🚀 Start Main Bot':
        if is_process_running("python3 main.py"):
            bot.send_message(message.chat.id, "⚠️ บอทหลักรันอยู่แล้ว")
        else:
            os.system(f"cd {BASE_DIR} && nohup python3 main.py > {LOG_PATH} 2>&1 &")
            bot.send_message(message.chat.id, "🚀 เปิดบอทหลักเรียบร้อย")

    elif message.text == '🚫 Stop Main Bot':
        os.system("pkill -15 -f 'python3 main.py'")
        bot.send_message(message.chat.id, "🛑 หยุดบอทหลักเรียบร้อย")

    elif message.text == '🔄 Restart Main Bot':
        bot.send_message(message.chat.id, "🔄 กำลังอัปเดตและรีสตาร์ทบอทหลัก...")
        
        # 1. ปิดตัวเก่า (SIGTERM เพื่อให้บอทส่งสถิติสุดท้ายก่อนปิด)
        os.system("pkill -15 -f 'python3 main.py'")
        time.sleep(3)
        
        # 2. ดึงโค้ดใหม่จาก Git
        pull_cmd = f"cd {BASE_DIR} && git fetch --all && git reset --hard origin/main"
        exit_code = os.system(pull_cmd)
        
        # 3. รันผ่านสคริปต์ Auto-Pilot เพื่อเช็ค Library ใหม่ๆ 
        if os.name == 'posix': # Linux
            run_cmd = f"cd {BASE_DIR} && chmod +x run_autopilot.sh && nohup ./run_autopilot.sh > {LOG_PATH} 2>&1 &"
        else: # Windows
            run_cmd = f"start /b run_autopilot.bat"
            
        os.system(run_cmd)
        
        time.sleep(5)
        if is_process_running("python3 main.py"):
            status = "✅ รีสตาร์ทบอทหลักสำเร็จ!"
            if exit_code != 0: status += "\n⚠️ หมายเหตุ: อัปเดต Git ไม่สำเร็จ"
            bot.send_message(message.chat.id, status)
        else:
            bot.send_message(message.chat.id, "❌ บอทไม่ทำงาน! โปรดเช็ค Log")

    elif message.text == '🔄 Restart Remote':
        bot.send_message(message.chat.id, "♻️ รีสตาร์ทรีโมท...")
        os._exit(0)

# --- Functions สำหรับรับค่าจากแชท ---
def update_min_size(message):
    try:
        val = float(message.text)
        c = load_config()
        c['SETTING']['MIN_SIZE_GB'] = val
        save_config(c)
        bot.send_message(message.chat.id, f"✅ อัปเดต Min Size เป็น `{val}` GB เรียบร้อย", parse_mode='Markdown')
    except:
        bot.send_message(message.chat.id, "❌ กรุณาส่งเป็นตัวเลขเท่านั้น")

def update_max_size(message):
    try:
        val = float(message.text)
        c = load_config()
        c['SETTING']['MAX_SIZE_GB'] = val
        save_config(c)
        bot.send_message(message.chat.id, f"✅ อัปเดต Max Size เป็น `{val}` GB เรียบร้อย", parse_mode='Markdown')
    except:
        bot.send_message(message.chat.id, "❌ กรุณาส่งเป็นตัวเลขเท่านั้น")

if __name__ == "__main__":
    print("🚀 Remote Bot is running...")
    bot.infinity_polling()