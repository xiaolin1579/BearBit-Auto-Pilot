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
import re
import psutil
from datetime import datetime, timedelta

# --- SETUP PATH & CONFIG ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
LOG_PATH = os.path.join(BASE_DIR, 'script_run.log')
STATS_HISTORY_FILE = os.path.join(BASE_DIR, "stats_history.json")

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

def get_bot_runtime(script_name="main.py"):
    """คำนวณเวลาที่บอททำงานมาแล้วจาก Process จริง"""
    # ดึงเฉพาะ cmdline มาเช็คก่อน เพื่อประหยัดทรัพยากร
    for proc in psutil.process_iter(['cmdline']):
        try:
            cmdline = proc.info.get('cmdline') or []
            if any(script_name in s for s in cmdline):
                # ✅ ใช้ .create_time() แทนการเรียกผ่าน info['start_time']
                create_time = proc.create_time() 
                start_time = datetime.fromtimestamp(create_time)
                duration = datetime.now() - start_time
                
                days = duration.days
                hours, remainder = divmod(duration.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                if days > 0:
                    return f"{days}d {hours}h {minutes}m"
                return f"{hours}h {minutes}m {seconds}s"
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return "0s"

def get_status_text():
    c = load_config()
    SET = c.get('SETTING', {})
    main_running = is_process_running("main.py")

    # ดึงค่า Run Time
    runtime = get_bot_runtime("main.py") if main_running else "N/A"

    # จัดรูปแบบข้อความ
    lines = [
        "📍 <b>System Status</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"• Main Bot: {'🟢 Online' if main_running else '🔴 Offline'}",
        f"• Run Time: <code>{runtime}</code>",
        f"• Min-Max: <code>{SET.get('MIN_SIZE_GB')} - {SET.get('MAX_SIZE_GB')} GB</code>",
        f"• Freeload Only: {'✅ Yes' if SET.get('FREELOAD_ENABLE') else '❌ No'}",
        "━━━━━━━━━━━━━━━━━━"
    ]
    return "\n".join(lines)

def format_size(size_gb):
    """
    แปลงค่าจากหน่วยพื้นฐาน (GB) ให้เป็นหน่วยที่เหมาะสมที่สุดโดยอัตโนมัติ
    รองรับตั้งแต่ KB ไปจนถึง PB
    """
    if size_gb == 0: return "0.00 GB"
    
    # แปลงจาก GB กลับไปเป็น Bytes ก่อนเพื่อให้เริ่มคำนวณจากหน่วยเล็กสุดได้แม่นยำ
    # (หรือจะเริ่มจาก GB เลยก็ได้ แต่การเริ่มจากหน่วยกลางๆ จะทำให้หารง่ายกว่า)
    units = ("B", "KB", "MB", "GB", "TB", "PB", "EB")
    
    # เริ่มต้นที่หน่วย GB (index 3 ในลิสต์ units)
    current_size = float(abs(size_gb))
    unit_index = 3 
    
    # ถ้าค่ามากกว่า 1024 ให้ขยับหน่วยขึ้น (เช่น GB -> TB)
    while current_size >= 1024 and unit_index < len(units) - 1:
        current_size /= 1024
        unit_index += 1
        
    # ถ้าค่าน้อยกว่า 1 (แต่ไม่ใช่ 0) ให้ขยับหน่วยลง (เช่น GB -> MB)
    while current_size < 1 and unit_index > 0:
        current_size *= 1024
        unit_index -= 1
        
    # คืนค่าพร้อมเครื่องหมาย (บวก/ลบ) ตามค่าเดิมที่ส่งมา
    sign = "-" if size_gb < 0 else ""
    return f"{sign}{current_size:.2f} {units[unit_index]}"

def parse_size(size_str):
    try:
        size_str = size_str.upper().replace(',', '')
        match = re.search(r"([0-9.]+)\s*(TB|GB|MB|KB|GIB|MIB|TIB)", size_str)
        if not match: return 0.0
        num, unit = float(match.group(1)), match.group(2)
        factors = {"TB": 1024, "TIB": 1024, "GB": 1, "GIB": 1, "MB": 1/1024, "MIB": 1/1024}
        return num * factors.get(unit, 1)
    except: return 0.0

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

def get_historical_report():
    try:
        if not os.path.exists(STATS_HISTORY_FILE):
            return "⚠️ ยังไม่มีไฟล์ประวัติสถิติในขณะนี้"

        with open(STATS_HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)

        now = datetime.now()
        curr_hour = now.strftime("%H")

        # 1. ข้อมูลปัจจุบัน
        snapshot = history.get(curr_hour)
        if not snapshot:
            return "⚠️ ยังไม่มีข้อมูลประวัติสำหรับชั่วโมงนี้"

        curr = snapshot.get('data')
        user_display = curr.get('username', 'BearBit User')

        def calc_diff(new_str, old_str):
            if not new_str or not old_str: return "➖ 0.00 GB"
            try:
                n = parse_size(new_str)
                o = parse_size(old_str)
                diff = n - o
                readable_val = format_size(diff)
                
                if diff > 0: 
                    return f"📈 +{readable_val}"
                elif diff < 0: 
                    return f"📉 {readable_val}"
                else: return "➖ 0.00 GB"
            except: return "➖ 0.00 GB"

        # 2. ข้อมูลย้อนหลัง 1 ชม.
        prev_hour = (now - timedelta(hours=1)).strftime("%H")
        h1 = history.get(prev_hour, {}).get('data')
        up_diff_h1 = calc_diff(curr['up'], h1['up']) if h1 else "N/A"
        dl_diff_h1 = calc_diff(curr['dl'], h1['dl']) if h1 else "N/A"

        # 3. ⚡ ข้อมูลย้อนหลัง (Accumulated/24 Hours)
        # หาเวลาที่เก่าที่สุดที่มีในไฟล์ history เพื่อใช้เป็นจุดตั้งต้น
        all_snapshots = []
        for h in history:
            t_str = history[h].get('time', '')
            if t_str:
                t_obj = datetime.strptime(t_str, "%Y-%m-%d %H:%M:%S")
                all_snapshots.append((t_obj, history[h].get('data')))

        # เรียงลำดับตามเวลา (เก่าไปใหม่)
        all_snapshots.sort(key=lambda x: x[0])

        if all_snapshots:
            oldest_time, oldest_data = all_snapshots[0]
            time_diff = (now - oldest_time).total_seconds()

            # ถ้าข้อมูลเก่าสุดนั้นมีอายุมากกว่า 10 นาที (ป้องกันลบกับตัวเองในนาทีแรก)
            if time_diff > 600:
                up_diff_24h = calc_diff(curr['up'], oldest_data['up'])
                dl_diff_24h = calc_diff(curr['dl'], oldest_data['dl'])

                # เปลี่ยนหัวข้อตามระยะเวลาที่มีข้อมูล
                if time_diff < 82800: # ยังไม่ครบ 23 ชม.
                    label_24h = f"⏳ <b>Accumulated ({int(time_diff//3600)}h {int((time_diff%3600)//60)}m)</b>"
                else:
                    label_24h = "📅 <b>Last 24 Hours</b>"
            else:
                up_diff_24h = dl_diff_24h = "Collecting..."
                label_24h = "📅 <b>Last 24 Hours</b>"
        else:
            up_diff_24h = dl_diff_24h = "N/A"
            label_24h = "📅 <b>Last 24 Hours</b>"

        msg = [
            "📊 <b>BearBit 24H Performance</b>",
            "━━━━━━━━━━━━━━━━━━",
            f"👤 <b>User:</b> <code>{user_display}</code>",
            f"📤 Uploaded: <code>{curr['up']}</code>",
            f"📥 Downloaded: <code>{curr['dl']}</code>",
            f"💰 Bonus: <code>{curr['bonus']}</code>",
            "━━━━━━━━━━━━━━━━━━",
            "⚡ <b>Last 1 Hour</b>",
            f"  └ 📤 {up_diff_h1}",
            f"  └ 📥 {dl_diff_h1}",
            "━━━━━━━━━━━━━━━━━━",
            f"{label_24h}", # ใช้ Label ที่คำนวณไว้
            f"  └ 📤 {up_diff_24h}",
            f"  └ 📥 {dl_diff_24h}",
            "━━━━━━━━━━━━━━━━━━"
        ]
        return "\n".join(msg)
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

def format_report(report_raw, platform='tg'):
    if platform == 'dc':
        # เปลี่ยน HTML เป็น Markdown สำหรับ Discord
        return report_raw.replace('<b>', '**').replace('</b>', '**')\
                         .replace('<code>', '`').replace('</code>', '`')
    return report_raw # ส่ง HTML ไปตามปกติสำหรับ Telegram

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
                m.add('📊 Status Check', '📈 Stats Report', '⚙️ Config Settings', '📄 View Log', '📁 Download Log', '🎮 Bot Controls')
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
                    await tg_bot.send_message(chat_id, get_status_text(), parse_mode='HTML')
                elif txt == '📈 Stats Report':
                    await tg_bot.send_message(chat_id, get_historical_report(), parse_mode='HTML')
                elif txt == '⚙️ Config Settings':
                    await tg_bot.send_message(chat_id, "🛠️ ตั้งค่าการกรองไฟล์", reply_markup=settings_menu())
                elif txt == '🎮 Bot Controls':
                    await tg_bot.send_message(chat_id, "🕹️ ควบคุมระบบ", reply_markup=controls_menu())
                elif txt == '⬅️ Back':
                    await tg_bot.send_message(chat_id, "🏠 กลับหน้าหลัก", reply_markup=main_menu())
                elif txt == '📄 View Log':
                    await tg_bot.send_message(chat_id, f"📄 **Last Log:**\n```\n{get_filtered_logs()}\n```", parse_mode='Markdown')
                elif txt == '📁 Download Log':
                    if os.path.exists(LOG_PATH):
                        try:
                            with open(LOG_PATH, 'rb') as f:
                                # ✅ สำหรับ AsyncTeleBot ให้ส่ง f ไปตรงๆ
                                # หากต้องการระบุชื่อไฟล์ให้ใช้ tuple (ชื่อไฟล์, ไฟล์ข้อมูล)
                                await tg_bot.send_document(
                                    chat_id,
                                    document=(os.path.basename(LOG_PATH), f),
                                    caption="📄 Full Log"
                                )
                        except Exception as e:
                            await tg_bot.send_message(chat_id, f"❌ เกิดข้อผิดพลาดในการส่งไฟล์: {e}")
                    else:
                        await tg_bot.send_message(chat_id, "❌ ไม่พบไฟล์ Log")

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
                    if is_process_running("main.py"):
                        await tg_bot.send_message(chat_id, "⚠️ บอทหลักทำงานอยู่ในขณะนี้")
                    else:
                        try:
                            # 1. แจ้งก่อนเริ่มงาน
                            await tg_bot.send_message(chat_id, "⏳ กำลังรันบอทหลัก...")

                            if os.name != 'nt':  # Linux/Unix
                                run_cmd = f"nohup ./run_autopilot.sh > {LOG_PATH} 2>&1 &"
                                subprocess.Popen(run_cmd, shell=True, cwd=BASE_DIR, preexec_fn=os.setpgrp)
                            else:  # Windows
                                run_cmd = f'start /b "" "run_autopilot.bat"'
                                subprocess.Popen(run_cmd, shell=True, cwd=BASE_DIR)

                            # 2. หน่วงเวลาเพื่อให้ Process เริ่มทำงาน (3 วินาที)
                            await asyncio.sleep(3)

                            # 3. ตรวจสอบอีกรอบว่ารันสำเร็จหรือไม่
                            if is_process_running("main.py"):
                                await tg_bot.send_message(chat_id, "✅ บอทหลักทำงานแล้ว")
                            else:
                                await tg_bot.send_message(chat_id, "❌ <b>รันบอทไม่สำเร็จ:</b> ไม่พบโปรเซสในระบบ โปรดเช็ค Log", parse_mode='HTML')

                        except Exception as e:
                            await tg_bot.send_message(chat_id, f"❌ <b>Error:</b> {str(e)}", parse_mode='HTML')
                elif txt == '🚫 Stop Bot':
                    if not is_process_running("main.py"):
                        await tg_bot.send_message(chat_id, "⚠️ บอทหลักไม่ได้ทำงานอยู่ในขณะนี้")
                    else:
                        try:
                            await tg_bot.send_message(chat_id, "⏳ กำลังส่งสัญญาณหยุดบอทหลัก...")

                            if os.name != 'nt':  # Linux/Unix
                                # ใช้ SIGTERM (15) เพื่อให้บอทเคลียร์งานก่อนปิด หรือ SIGKILL (9) ถ้าต้องการปิดทันที
                                stop_cmd = "pkill -15 -f 'main.py'"
                                os.system(stop_cmd)
                            else:  # Windows
                                # ✅ แก้ไข: ใช้ WMIC หรือ Taskkill แบบระบุชื่อไฟล์สคริปต์
                                # เพื่อไม่ให้มันไปฆ่า Python ตัวอื่นๆ (เช่น บอทรีโมทตัวนี้)
                                stop_cmd = 'wmic process where "commandline like \'%main.py%\'" delete'
                                os.system(stop_cmd)

                            # หน่วงเวลาให้ระบบเคลียร์ Process
                            await asyncio.sleep(3)

                            # ตรวจสอบอีกครั้ง
                            if not is_process_running("main.py"):
                                await tg_bot.send_message(chat_id, "🛑 หยุดบอทหลักสำเร็จแล้ว")
                            else:
                                await tg_bot.send_message(chat_id, "❌ <b>ไม่สามารถหยุดบอทได้:</b> โปรเซสยังค้างอยู่ในระบบ", parse_mode='HTML')

                        except Exception as e:
                            await tg_bot.send_message(chat_id, f"❌ <b>Error:</b> {str(e)}", parse_mode='HTML')
                elif txt == '🔄 Restart & Update':
                    await tg_bot.send_message(chat_id, "⏳ กำลังเริ่มกระบวนการ Update...")

                    try:
                        # 1. ปิดบอทเดิมก่อน
                        if is_process_running("main.py"):
                            stop_cmd = "pkill -15 -f 'main.py'" if os.name != 'nt' else 'wmic process where "commandline like \'%main.py%\'" delete'
                            os.system(stop_cmd)
                            await asyncio.sleep(3) # รอให้ Process คลายตัว

                        # 2. ดึงโค้ดใหม่จาก Git
                        # ใช้ && เพื่อให้มั่นใจว่าคำสั่งถัดไปจะรันเมื่อคำสั่งก่อนหน้าสำเร็จเท่านั้น
                        git_cmd = f"cd {BASE_DIR} && git fetch --all && git reset --hard origin/main"
                        git_result = os.system(git_cmd)

                        if git_result != 0:
                            await tg_bot.send_message(chat_id, "⚠️ <b>Git Update Failed:</b> ตรวจสอบการเชื่อมต่อหรือ Git Conflict", parse_mode='HTML')
                            # ไม่ควรไปต่อถ้ารีเซ็ตโค้ดไม่สำเร็จ
                        else:
                            await tg_bot.send_message(chat_id, "📥 ดึงโค้ดเวอร์ชันล่าสุดสำเร็จ... กำลังเริ่มบอทใหม่")

                        # 3. รันบอทใหม่ (ใช้ Popen เพื่อความเสถียร)
                        if os.name != 'nt':
                            run_cmd = f"nohup ./run_autopilot.sh > {LOG_PATH} 2>&1 &"
                            subprocess.Popen(run_cmd, shell=True, cwd=BASE_DIR, preexec_fn=os.setpgrp)
                        else:
                            run_cmd = 'start /b "" "run_autopilot.bat"'
                            subprocess.Popen(run_cmd, shell=True, cwd=BASE_DIR)

                        # 4. ตรวจสอบสถานะสุดท้าย
                        await asyncio.sleep(5)
                        if is_process_running("main.py"):
                            await tg_bot.send_message(chat_id, "✅ <b>Update & Restart Success!</b>\nบอทหลักกลับมาทำงานปกติแล้ว", parse_mode='HTML')
                        else:
                            await tg_bot.send_message(chat_id, "❌ <b>Update Error:</b> บอทไม่ออนไลน์หลังอัปเดต โปรดตรวจสอบ Log")

                    except Exception as e:
                        await tg_bot.send_message(chat_id, f"❌ <b>Update System Error:</b> {str(e)}")
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
                    await ctx.send(format_report(get_status_text(), platform='dc'))

            @dc_bot.command(name="report")
            async def dc_status(ctx):
                if ctx.author.id == DC_ADMIN_ID:
                    await ctx.send(format_report(get_historical_report(), platform='dc'))

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
