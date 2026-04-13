import telebot
from telebot import types
from telebot.async_telebot import AsyncTeleBot
import discord
from discord.ext import commands
import asyncio
import os
import json
import subprocess
import time

# --- SETUP PATH & CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
LOG_PATH = os.path.join(BASE_DIR, 'script_run.log')

# ตัวแปรเก็บสถานะการทำงานของ User (สำหรับ Async)
user_states = {} # { chat_id: "WAITING_MIN_SIZE" }

def load_config():
    if not os.path.exists(CONFIG_PATH): return {}
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

# --- SHARED FUNCTIONS ---
def is_process_running(name):
    try:
        if os.name == 'nt': # Windows
            cmd = 'tasklist /FI "IMAGENAME eq python.exe"'
            output = subprocess.check_output(cmd, shell=True).decode()
            return name in output
        else: # Linux/macOS
            output = subprocess.check_output(["ps", "aux"]).decode()
            return name in output
    except: return False

def get_status_text():
    c = load_config()
    SET = c.get('SETTING', {})
    main_running = is_process_running("main.py")
    return (f"📍 **System Status**\n"
            f"• Main Bot: `{'🟢 Online' if main_running else '🔴 Offline'}`\n"
            f"• Min-Max: `{SET.get('MIN_SIZE_GB')} - {SET.get('MAX_SIZE_GB')} GB`\n"
            f"• Freeload Only: `{'✅ Yes' if SET.get('FREELOAD_ENABLE') else '❌ No'}`")

def get_filtered_logs(n=15):
    if not os.path.exists(LOG_PATH): return "❌ ไม่พบไฟล์ Log"
    try:
        if os.name != 'nt':
            raw_logs = subprocess.check_output(["tail", "-n", "50", LOG_PATH]).decode('utf-8')
            lines = raw_logs.split('\n')
        else:
            with open(LOG_PATH, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        filtered = [l for l in lines if "Next cycle in" not in l and l.strip() != ""]
        return "\n".join(filtered[-n:])
    except: return "⚠️ อ่าน Log ขัดข้อง"

# --- MAIN RUNNER ---
async def main():
    CONF = load_config()
    tasks = []
    print("🚀 Initializing Hybrid Remote Control...")

    # --- 🔵 TELEGRAM SECTION ---
    tg_cfg = CONF.get('TELEGRAM_CONFIG', {})
    if tg_cfg.get('remote_enable', False):
        try:
            tg_bot = AsyncTeleBot(tg_cfg['remote_bot_token'])
            TG_CHAT_ID = str(tg_cfg['chat_id'])

            def main_menu():
                m = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
                m.add('📊 Status Check', '⚙️ Config Settings', '📄 View Log', '📁 Download Log', '🎮 Bot Controls')
                return m

            def settings_menu():
                m = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
                m.add('📏 Set Min Size', '📐 Set Max Size')
                m.add('♻️ Toggle Freeload', '⬅️ Back')
                return m

            def controls_menu():
                m = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
                m.add('🚀 Start Bot', '🚫 Stop Bot')
                m.add('🔄 Restart & Update', '♻️ Restart Remote', '⬅️ Back')
                return m

            @tg_bot.message_handler(commands=['start'])
            async def tg_start(message):
                if str(message.chat.id) == TG_CHAT_ID:
                    await tg_bot.send_message(message.chat.id, "🕹️ BearBit Remote Online", reply_markup=main_menu())

            # --- เพิ่มส่วนการดึงข้อมูลบอทเพื่อโชว์ตอน Online ---
            async def get_bot_info():
                bot_info = await tg_bot.get_me()
                print(f"📡 Telegram Remote Online as: @{bot_info.username}")

            # เรียกใช้งาน function แจ้งเตือนสถานะ
            import asyncio
            asyncio.create_task(get_bot_info())

            @tg_bot.message_handler(func=lambda m: True)
            async def tg_handle(message):
                chat_id = str(message.chat.id)
                if chat_id != TG_CHAT_ID: return
                txt = message.text

                # --- 1. ตรวจสอบสถานะการรอรับค่า (State Management) ---
                if chat_id in user_states:
                    state = user_states[chat_id]
                    try:
                        val = float(txt)
                        c = load_config()
                        if 'SETTING' not in c: c['SETTING'] = {}

                        if state == "WAIT_MIN":
                            c['SETTING']['MIN_SIZE_GB'] = val
                            await tg_bot.send_message(chat_id, f"✅ อัปเดต Min Size: `{val}` GB", parse_mode='Markdown', reply_markup=settings_menu())
                        elif state == "WAIT_MAX":
                            c['SETTING']['MAX_SIZE_GB'] = val
                            await tg_bot.send_message(chat_id, f"✅ อัปเดต Max Size: `{val}` GB", parse_mode='Markdown', reply_markup=settings_menu())

                        save_config(c)
                        del user_states[chat_id]
                        return
                    except ValueError:
                        await tg_bot.send_message(chat_id, "❌ กรุณาส่งเป็นตัวเลขเท่านั้น (เช่น 10.5) หรือส่งข้อความอื่นเพื่อยกเลิก")
                        del user_states[chat_id]
                        return

                # --- 2. เมนูหลัก ---
                if txt == '📊 Status Check':
                    await tg_bot.send_message(chat_id, get_status_text(), parse_mode='Markdown')
                elif txt == '⚙️ Config Settings':
                    await tg_bot.send_message(chat_id, "🛠️ ตั้งค่าการกรองไฟล์", reply_markup=settings_menu())
                elif txt == '🎮 Bot Controls':
                    await tg_bot.send_message(chat_id, "🕹️ ควบคุมระบบ", reply_markup=controls_menu())
                elif txt == '⬅️ Back':
                    await tg_bot.send_message(chat_id, "🏠 กลับหน้าหลัก", reply_markup=main_menu())
                elif txt == '📄 View Log':
                    await tg_bot.send_message(chat_id, f"📄 **Last Log:**\n```\n{get_filtered_logs()}\n```", parse_mode='Markdown')

                # --- Config Actions ---
                elif txt == '📏 Set Min Size':
                    user_states[chat_id] = "WAIT_MIN"
                    await tg_bot.send_message(chat_id, "📏 ส่งตัวเลขขนาดไฟล์ **ขั้นต่ำ** (GB):", reply_markup=types.ReplyKeyboardRemove())
                elif txt == '📐 Set Max Size':
                    user_states[chat_id] = "WAIT_MAX"
                    await tg_bot.send_message(chat_id, "📐 ส่งตัวเลขขนาดไฟล์ **สูงสุด** (GB):", reply_markup=types.ReplyKeyboardRemove())
                elif txt == '♻️ Toggle Freeload':
                    c = load_config()
                    if 'SETTING' not in c: c['SETTING'] = {}
                    curr = c['SETTING'].get('FREELOAD_ENABLE', True)
                    c['SETTING']['FREELOAD_ENABLE'] = not curr
                    save_config(c)
                    await tg_bot.send_message(chat_id, f"✅ Freeload: `{'ON' if not curr else 'OFF'}`", parse_mode='Markdown')

                # --- Control Actions ---
                elif txt == '🚀 Start Bot':
                    if is_process_running("main.py"): await tg_bot.send_message(chat_id, "⚠️ บอทรันอยู่แล้ว")
                    else:
                        run_cmd = f"cd {BASE_DIR} && nohup ./run_autopilot.sh > {LOG_PATH} 2>&1 &" if os.name != 'nt' else f'start /b "" "{os.path.join(BASE_DIR, "run_autopilot.bat")}"'
                        os.system(run_cmd)
                        await tg_bot.send_message(chat_id, "🚀 กำลังเริ่มบอท...")
                elif txt == '🚫 Stop Bot':
                    stop_cmd = "pkill -15 -f 'main.py'" if os.name != 'nt' else 'taskkill /F /FI "IMAGENAME eq python.exe"'
                    os.system(stop_cmd)
                    await tg_bot.send_message(chat_id, "🛑 สั่งหยุดบอทหลักแล้ว")
                elif txt == '🔄 Restart & Update':
                    await tg_bot.send_message(chat_id, "🔄 ปิดบอทและดึงโค้ดใหม่จาก Git...")
                    os.system("pkill -15 -f 'main.py'")
                    os.system(f"cd {BASE_DIR} && git fetch --all && git reset --hard origin/main")
                    await asyncio.sleep(2)
                    os.system(f"cd {BASE_DIR} && nohup ./run_autopilot.sh > {LOG_PATH} 2>&1 &")
                    await tg_bot.send_message(chat_id, "✅ อัปเดตและเริ่มบอทใหม่เรียบร้อย")
                elif txt == '♻️ Restart Remote':
                    await tg_bot.send_message(chat_id, "♻️ รีสตาร์ท Remote...")
                    os._exit(0)
                elif txt == '⬅️ Back':
                    await tg_bot.send_message(chat_id, "🏠 กลับหน้าหลัก", reply_markup=main_menu())

            tasks.append(tg_bot.polling(non_stop=True))
        except Exception as e: print(f"❌ TG Error: {e}")

    # --- 🟣 DISCORD SECTION (ปรับปรุงให้รองรับ @mention สมบูรณ์) ---
    dc_cfg = CONF.get('DISCORD_CONFIG', {})
    if dc_cfg.get('remote_enable', False):
        try:
            intents = discord.Intents.default()
            intents.message_content = True  # สำคัญมาก ต้องเปิดใน Portal ด้วย

            # ใช้ prefix เป็น ! และรองรับการแท็ก
            dc_bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"), intents=intents)
            DC_ADMIN_ID = int(dc_cfg.get('admin_id', 0))

            @dc_bot.event
            async def on_ready():
                print(f"✅ Discord Remote Online as: {dc_bot.user}")

            # --- เพิ่มส่วนนี้เพื่อดักจับการ @mention โดยเฉพาะ ---
            @dc_bot.event
            async def on_message(message):
                if message.author == dc_bot.user: return # ไม่ตอบโต้บอทตัวเอง

                # ตรวจสอบว่าบอทถูกแท็กหรือไม่
                if dc_bot.user.mentioned_in(message):
                    content = message.content.lower()
                    # ถ้าแท็กบอทแล้วมีคำว่า status หรือ log ให้ทำงานทันที
                    if "status" in content:
                        if message.author.id == DC_ADMIN_ID:
                            await message.channel.send(get_status_text())
                        else:
                            await message.channel.send(f"⚠️ ID ของคุณคือ `{message.author.id}`")
                        return # จบการทำงานตรงนี้เลย

                    elif "log" in content:
                        if message.author.id == DC_ADMIN_ID:
                            await message.channel.send(f"📄 **Logs:**\n```\n{get_filtered_logs()}\n```")
                        return

                # สำคัญ: ต้องมีบรรทัดนี้เพื่อให้คำสั่งแบบ !status ยังทำงานได้ปกติ
                await dc_bot.process_commands(message)

            @dc_bot.command(name="status")
            async def dc_status(ctx):
                if ctx.author.id == DC_ADMIN_ID:
                    await ctx.send(get_status_text())

            @dc_bot.command(name="log")
            async def dc_log(ctx):
                if ctx.author.id == DC_ADMIN_ID:
                    await ctx.send(f"📄 **Logs:**\n```\n{get_filtered_logs()}\n```")

            tasks.append(dc_bot.start(dc_cfg['remote_bot_token']))
        except Exception as e: print(f"❌ Discord Error: {e}")
    if tasks: await asyncio.gather(*tasks)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
