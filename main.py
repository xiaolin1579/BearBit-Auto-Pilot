import random
import time
import os
import re
import hashlib
import json
import requests
import urllib3
import base64
import signal
import sys
import platform
import shutil
import pytz
import xml.etree.ElementTree as ET
from datetime import datetime
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import functools
print = functools.partial(print, flush=True)

def handle_exit(sig, frame):
    reasons = {
        signal.SIGINT: "User Interrupted (Ctrl+C)",
        signal.SIGHUP: "Terminal Closed (SIGHUP)",
        signal.SIGTERM: "Process Killed (SIGTERM)"
    }
    reason = reasons.get(sig, f"Signal {sig}")
    stop_msg = f"🛑 BearBit Auto-Pilot : Stopped\nReason: {reason}"
    print(f"\n{stop_msg}")
    try: send_notify(stop_msg)
    except: pass
    os._exit(0)

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)
if sys.platform != "win32":
    signal.signal(signal.SIGHUP, handle_exit)
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer)

urllib3.disable_warnings()

# ========================= CONFIGURATION =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(BASE_DIR, "seen.txt")
HASH_SEEN_FILE = os.path.join(BASE_DIR, "hash_seen.txt")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATS_CACHE_FILE = os.path.join(BASE_DIR, "stats_cache.json")
STATS_HISTORY_FILE = os.path.join(BASE_DIR, "stats_history.json")
CFG = {} 
ORIGINAL_SETTING = None

def load_full_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"❌ Error: ไม่พบไฟล์ {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def send_notify(msg, raw_data=None):
    """
    ส่งแจ้งเตือนผ่าน Messaging API, Telegram และ Discord DM
    """
    cfg = load_full_config()
    msg = msg.strip()

    # เตรียมข้อความ
    discord_msg = msg.replace('<b>', '**').replace('</b>', '**')
    line_clean_msg = msg.replace('<b>', '').replace('</b>', '')

    # 1. LINE Messaging API (คงเดิม)
    line_cfg = cfg.get('LINE_CONFIG', {})
    if line_cfg.get('enable') and line_cfg.get('access_token'):
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_cfg.get('access_token')}"
        }
        payload = {
            "to": line_cfg.get('user_id'),
            "messages": [{"type": "text", "text": line_clean_msg}]
        }
        try: requests.post(url, json=payload, headers=headers, timeout=10)
        except: pass

    # 2. Telegram Bot (คงเดิม)
    tele_cfg = cfg.get('TELEGRAM_CONFIG', {})
    if tele_cfg.get('notify_enable') and tele_cfg.get('main_bot_token'):
        try:
            requests.post(
                f"https://api.telegram.org/bot{tele_cfg.get('main_bot_token')}/sendMessage",
                json={'chat_id': tele_cfg.get('chat_id'), 'text': msg, 'parse_mode': 'HTML'},
                timeout=10
            )
        except: pass

    # 3. Discord DM (ปรับปรุงใหม่)
    disc_cfg = cfg.get('DISCORD_CONFIG', {})
    bot_token = disc_cfg.get('remote_bot_token') # ใช้ Token เดียวกับบอทรีโมท
    admin_id = disc_cfg.get('admin_id')

    if disc_cfg.get('notify_enable') and bot_token and admin_id:
        try:
            # ขั้นตอนที่ 1: สร้าง DM Channel กับ Admin
            create_dm_url = "https://discord.com/api/v10/users/@me/channels"
            headers = {
                "Authorization": f"Bot {bot_token}",
                "Content-Type": "application/json"
            }
            # ส่ง recipient_id (Admin ID) เพื่อขอเปิดห้องแชท
            dm_channel_res = requests.post(create_dm_url, json={"recipient_id": str(admin_id)}, headers=headers, timeout=10)

            if dm_channel_res.status_code == 200:
                channel_id = dm_channel_res.json().get('id')
                # ขั้นตอนที่ 2: ส่งข้อความเข้าไปใน Channel ID ที่ได้มา
                send_msg_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                payload = {
                    "content": f"🔔 **[BearBit Notification]**\n{discord_msg}"
                }
                requests.post(send_msg_url, json=payload, headers=headers, timeout=10)
        except Exception as e:
            print(f"⚠️ Discord DM Notify Error: {e}")

# กำหนด Timezone ไทย
tz = pytz.timezone('Asia/Bangkok')

def get_now():
    """ฟังก์ชันกลางสำหรับดึงเวลาไทยปัจจุบัน"""
    return datetime.now(tz)
    
def load_data(path):
    if not os.path.exists(path): return set()
    with open(path, "r", encoding='utf-8') as f: return set(x.strip().lower() for x in f if x.strip())

def save_data(path, data):
    with open(path, "w", encoding='utf-8') as f: f.write("\n".join(sorted(list(data))))

def extract_info_hash(torrent_content):
    try:
        start = torrent_content.find(b'4:info') + 6
        if start < 6: return None
        return hashlib.sha1(torrent_content[start:-1]).hexdigest().lower()
    except: return None

def parse_size(size_str):
    try:
        size_str = size_str.upper().replace(',', '')
        match = re.search(r"([0-9.]+)\s*(TB|GB|MB|KB|GIB|MIB|TIB)", size_str)
        if not match: return 0.0
        num, unit = float(match.group(1)), match.group(2)
        factors = {"TB": 1024, "TIB": 1024, "GB": 1, "GIB": 1, "MB": 1/1024, "MIB": 1/1024}
        return num * factors.get(unit, 1)
    except: return 0.0

def check_freeload_status(row):
    """
    เวอร์ชั่นแก้ไขตามโครงสร้าง HTML จริง:
    ค่าฟรี (35%) อยู่ที่ Index 3
    """
    cells = row.find_all("td")

    # สแกนตั้งแต่ Index 3 เป็นต้นไป (เพราะ index 0-2 คือหมวดหมู่/รูป/ชื่อไฟล์)
    # เราจะสแกนไปจนถึงช่องที่ 8 เพื่อความปลอดภัย
    for cell in cells[3:8]:
        cell_html = str(cell).lower()
        cell_text = cell.get_text(strip=True)

        # 1. เช็คสัญลักษณ์รูปภาพที่เป็น Free 100%
        if any(x in cell_html for x in ["pic/s-free.gif", "pic/s-x2.gif", "pic/s-x6.gif"]):
            return 100

        # 2. ค้นหาตัวเลข % (เช่น 35% ใน <font color=green><b>35%</b></font>)
        match = re.search(r"(\d+)\s*%", cell_text)
        if match:
            return int(match.group(1))

        # 3. ถ้าเจอ "No" ในช่องนี้ และยังไม่เจอ % ให้สันนิษฐานว่า 0
        # แต่ยังไม่ return ทันที เผื่อช่องถัดไปมี %
        if "no" in cell_text.lower():
            continue

    return 0

def check_pending_status(session, base_url, t_id):
    try:
        detail_url = f"{base_url}/details.php?id={t_id}"
        r = session.get(detail_url, timeout=10, verify=False)
        if r.status_code == 200:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, 'html.parser')
            # มองหาแถวที่มีคำว่า "ฟรีโหลด" หรือสถานะการดาวน์โหลด
            # BearBit มักจะใช้ตารางในการแสดงผล
            page_text = soup.get_text()
            if "(รอการอนุมัติ)" in page_text:
                return True
        return False
    except Exception as e:
        print(f"      ⚠️ Error checking details: {e}")
        return False

# ========================= BROWSER ENGINE =========================

def get_universal_browser():
    current_os = platform.system().lower()
    if current_os == "windows":
        search_map = {
            "chromium": [os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"), os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe")],
            "firefox": [os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe")]
        }
    else:
        search_map = {
            "chromium": ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/usr/bin/chromium-browser"],
            "firefox": ["/usr/bin/firefox", "/usr/bin/firefox-esr"]
        }
    for path in search_map["chromium"]:
        if os.path.exists(path): return {"type": "chromium", "path": path}
    for path in search_map["firefox"]:
        if os.path.exists(path): return {"type": "firefox", "path": path}
    return None

def launch_any_browser(p):
    info = get_universal_browser()
    common_args = ["--no-sandbox", "--disable-gpu", "--mute-audio"]
    if not info: return p.chromium.launch(headless=True, args=common_args), "Default Playwright"
    if info["type"] == "chromium":
        return p.chromium.launch(executable_path=info["path"], headless=True, args=common_args + ["--disable-dev-shm-usage"]), info["path"]
    else:
        return p.firefox.launch(executable_path=info["path"], headless=True, args=common_args), info["path"]

# ========================= NODE CLASSES =========================

class QbitNode:
    def __init__(self, cfg):
        self.name, self.url = cfg["name"], cfg["url"].rstrip("/")
        self.user, self.pw = cfg["qb_user"], cfg["qb_pass"]
        self.quota_gb = cfg.get("quota_gb", 0)
        self.auth = HTTPBasicAuth(self.user, self.pw) if cfg.get("nginx") else None
        self.s = requests.Session()
        self.free_gb = 0
        self.is_connected = False
        self.jobs = 0
        self.stat_msg = "Active/Total: 0/0"

    def login(self):
        try:
            r = self.s.post(f"{self.url}/api/v2/auth/login", data={"username": self.user, "password": self.pw}, auth=self.auth, verify=False, timeout=10)
            self.is_connected = (r.status_code == 200 and ("Ok." in r.text or r.cookies.get('SID')))
            return self.is_connected
        except: return False

    def refresh_status(self):
        if not self.is_connected: return False
        try:
            # ดึงข้อมูล Torrent ทั้งหมด
            torrents = self.s.get(f"{self.url}/api/v2/torrents/info", auth=self.auth, verify=False, timeout=10).json()
            used_gb = sum(t.get('size', 0) for t in torrents) / (1024**3)

            # ดึงขนาดที่กำลังโหลดค้างอยู่ (Bytes ที่เหลือ)
            pending_gb = self.get_downloading_size()
            safety_buffer = 15.0

            if self.quota_gb > 0:
                # กรณีมี Quota: พื้นที่ว่าง = Quota - ที่ใช้ไปแล้ว - ที่รอโหลด - Buffer
                self.free_gb = max(0, self.quota_gb - used_gb - pending_gb - safety_buffer)
            else:
                # กรณีใช้ทั้ง Disk: พื้นที่ว่าง = พื้นที่ Disk จริง - ที่รอโหลด - Buffer
                r_main = self.s.get(f"{self.url}/api/v2/sync/maindata", auth=self.auth, verify=False, timeout=10).json()
                real_disk_free = r_main.get('server_state', {}).get('free_space_on_disk', 0) / (1024**3)
                self.free_gb = max(0, real_disk_free - pending_gb - safety_buffer)

            self.stat_msg = f"Used: {used_gb:.1f}GB | Pending: {pending_gb:.1f}GB | Safe: {self.free_gb:.1f}GB"
            return True
        except Exception as e:
            print(f"⚠️ [{self.name}] Refresh Status Error: {e}")
            return False

    def add(self, content, size=None, n_cfg=None):
        try:
            if len(content) < 1000: return False

            files = {"torrents": ("f.torrent", content, "application/x-bittorrent")}
            data = {
                "paused": "false",
                "firstLastPiecePrio": "true",
                "category": "BearBit-Auto",
                "tags": "AutoPilot"
            }

            r = self.s.post(f"{self.url}/api/v2/torrents/add", files=files, data=data, auth=self.auth, verify=False, timeout=30)

            if r.status_code == 200 and "Ok" in r.text:
                return True
            else:
                # พ่น Error จากฝั่ง Server เมื่อ API ตอบกลับแต่ไม่ใช่ Ok
                print(f"⚠️ [API Error] {self.url}: {r.status_code} - {r.text}")
                return False
        except Exception as e:
            # พ่น Error เมื่อเกิดปัญหาที่ตัวบอทเอง (เช่น Timeout หรือ Connection Error)
            print(f"❌ [Exception] {self.url}: {str(e)}")
            return False

    def get_all_torrents_info(self):
        try:
            r = self.s.get(f"{self.url}/api/v2/torrents/info", params={'filter': 'completed'}, timeout=10)
            if r.status_code == 200:
                data = r.json()
                # แนะนำให้ Sort ตาม Ratio จากมากไปน้อย (ไฟล์ที่คุ้มแล้วอยู่บน)
                data.sort(key=lambda x: x['ratio'], reverse=True)

                return [
                    {
                        'hash': t['hash'],
                        'ratio': t['ratio'],
                        'name': t['name'],
                        'size': t['size'] / (1024**3), # เก็บขนาดไว้คำนวณพื้นที่ที่จะได้คืน
                        'added_on': t['added_on']
                    } for t in data
                ]
            return []
        except: return []

    def is_torrent_exists(self, t_hash):
        if not self.is_connected: self.login()
        try:
            # ตรวจสอบจาก hash โดยตรงผ่าน API ของ qBittorrent
            r = self.s.get(f"{self.url}/api/v2/torrents/info", params={'hashes': t_hash}, auth=self.auth, timeout=10)
            return r.status_code == 200 and len(r.json()) > 0
        except: return False

    def delete_torrent(self, hash_str):
        try:
            self.s.post(f"{self.url}/api/v2/torrents/delete", data={"hashes": hash_str, "deleteFiles": "true"}, auth=self.auth, verify=False, timeout=10)
            return True
        except: return False

    def get_downloading_size(self):
        try:
            # ดึงเฉพาะไฟล์ที่ยังโหลดไม่เสร็จ (downloading, stalledDL, metaDL)
            r = self.s.get(f"{self.url}/api/v2/torrents/info", params={'filter': 'downloading'}, timeout=10)
            if r.status_code == 200:
                # amount_left คือจำนวน Bytes ที่เหลือที่ต้องโหลดจนเต็ม
                total_remaining_bytes = sum(t.get('amount_left', 0) for t in r.json())
                return total_remaining_bytes / (1024**3) # คืนค่าเป็น GB
            return 0.0
        except:
            return 0.0
            
    def get_active_downloads(self):
        try:
            if not self.is_connected: self.login()

            results = []
            # ใช้การวน Loop ดึงทั้ง downloading และ checking
            for filter_type in ['downloading', 'checking']:
                r = self.s.get(f"{self.url}/api/v2/torrents/info", params={'filter': filter_type}, auth=self.auth, verify=False, timeout=10)

                if r.status_code == 200 and r.text:
                    try:
                        torrents = r.json()
                        for t in torrents:
                            results.append({
                                'hash': t.get('hash'),
                                'size_bytes': t.get('size', 0),
                                'state': t.get('state'),
                                'amount_left': t.get('amount_left', 0)
                            })
                    except:
                        continue # ถ้า Parse JSON ไม่ได้ให้ข้ามไปก่อน
                elif r.status_code in [401, 403]:
                    self.is_connected = False # สั่งให้ Login ใหม่ในรอบหน้า

            return results
        except Exception as e:
            self.is_connected = False
            return []

    def reannounce_all(self):
        """ สั่ง Re-announce ทุก Torrent ใน qBittorrent """
        if not self.is_connected and not self.login(): return False
        try:
            # สั่ง reannounce ทุก hashes โดยส่งค่า 'all'
            r = self.s.post(f"{self.url}/api/v2/torrents/reannounce", data={"hashes": "all"}, auth=self.auth, verify=False, timeout=10)
            return r.status_code == 200
        except: return False

class RtorrentNode:
    def __init__(self, cfg):
        self.name, self.url = cfg["name"], cfg["url"].rstrip("/")
        self.user, self.pw = cfg["rt_user"], cfg["rt_pass"]
        self.quota_gb = cfg.get("quota_gb", 0)
        self.auth = HTTPBasicAuth(self.user, self.pw)
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36',
            'Content-Type': 'text/xml'
        }
        self.free_gb = 0
        self.jobs = 0
        self.is_connected = False
        self.stat_msg = "Active/Total: 0/0"

    def login(self):
        try:
            # 1. ลอง Login ด้วย Basic Auth ก่อน
            r = requests.post(self.url, data='<?xml version="1.0"?><methodCall><methodName>system.listMethods</methodName></methodCall>', auth=self.auth, timeout=10)
            
            # 2. ถ้าเจอ 401 และเซิร์ฟเวอร์แจ้งว่าต้องการ Digest
            if r.status_code == 401 and 'digest' in r.headers.get('WWW-Authenticate', '').lower():
                # สลับไปใช้ Digest Auth ทันที
                self.auth = HTTPDigestAuth(self.user, self.pw)
                r = requests.post(self.url, data='<?xml version="1.0"?><methodCall><methodName>system.listMethods</methodName></methodCall>', auth=self.auth, headers=self.headers, timeout=10)
            
            self.is_connected = (r.status_code == 200)
            return self.is_connected
        except:
            return False

    def refresh_status(self):
        if not self.is_connected: return False
        try:
            # ดึงข้อมูลผ่าน XML-RPC
            xml = '<?xml version="1.0"?><methodCall><methodName>d.multicall2</methodName><params><param><value><string></string></value></param><param><value><string>main</string></value></param><param><value><string>d.is_active=</string></value></param><param><value><string>d.size_bytes=</string></value></param></params></methodCall>'
            r = requests.post(self.url, data=xml, auth=self.auth, headers=self.headers, timeout=10, verify=False)
            soup = BeautifulSoup(r.text, "xml")

            vals = [v.get_text() for v in soup.find_all("i8")]
            total, active, used_bytes = len(vals)//2, 0, 0
            for i in range(0, len(vals), 2):
                if int(vals[i]) == 1: active += 1
                used_bytes += int(vals[i+1])

            used_gb = used_bytes / (1024**3)
            # ดึงขนาดไฟล์ที่จองพื้นที่ไว้แล้วแต่ยังโหลดไม่เสร็จ
            pending_gb = self.get_downloading_size()
            safety_buffer = 15.0 # GB สำหรับป้องกัน Quota เต็ม 99%

            if self.quota_gb > 0:
                # พื้นที่ว่างจริง = Quota - ที่ใช้ไปแล้ว - ที่รอโหลดค้างอยู่ - Buffer กันเหนียว
                self.free_gb = max(0, self.quota_gb - used_gb - pending_gb - safety_buffer)
            else:
                # โหมดเช็คดิสก์จริงจาก Server
                r_free = requests.post(self.url, data='<?xml version="1.0"?><methodCall><methodName>network.disk_free</methodName></methodCall>', auth=self.auth, headers=self.headers, timeout=10, verify=False)
                real_free = abs(int(BeautifulSoup(r_free.text, "xml").find("value").get_text().strip())) / (1024**3)
                self.free_gb = max(0, real_free - pending_gb - safety_buffer)

            self.stat_msg = f"Used: {used_gb:.1f}GB | Pending: {pending_gb:.1f}GB | Safe: {self.free_gb:.1f}GB"
            return True
        except: return False

    def get_all_torrents_info(self):
        try:
            xml = '''<?xml version="1.0"?>
            <methodCall>
            <methodName>d.multicall2</methodName>
            <params>
                <param><value><string></string></value></param>
                <param><value><string>main</string></value></param>
                <param><value><string>d.hash=</string></value></param>
                <param><value><string>d.ratio=</string></value></param>
                <param><value><string>d.complete=</string></value></param>
                <param><value><string>d.name=</string></value></param>
            </params>
            </methodCall>'''

            r = requests.post(self.url, data=xml, auth=self.auth, headers=self.headers, timeout=20, verify=False)
            if r.status_code != 200: return []

            root = ET.fromstring(r.text)
            # rTorrent XML-RPC คืนค่าเป็น nested arrays
            data = root.findall(".//value/array/data/value/array/data")

            results = []
            for item in data:
                values = item.findall("./value")
                # values[0]=hash, [1]=ratio, [2]=complete, [3]=name
                is_complete = values[2].find("./i4").text == "1"

                if is_complete:
                    results.append({
                        'hash': values[0].find("./string").text,
                        'ratio': int(values[1].find("./i4").text) / 1000.0,
                        'name': values[3].find("./string").text
                    })
            return results
        except Exception as e:
            print(f"❌ rTorrent Reclaim Error: {e}")
            return []

    def is_torrent_exists(self, t_hash):
        if not self.is_connected: self.login()
        try:
            # ใช้ XML-RPC ตรวจสอบชื่อไฟล์หรือ hash (ในที่นี้ใช้ hash ซึ่งแม่นยำที่สุด)
            xml = f'<?xml version="1.0"?><methodCall><methodName>d.name</methodName><params><param><value><string>{t_hash.upper()}</string></value></param></params></methodCall>'
            r = requests.post(self.url, data=xml, auth=self.auth, headers=self.headers, timeout=10, verify=False)
            # ถ้า rTorrent คืนค่าสำเร็จ (ไม่ error) แสดงว่ามีไฟล์อยู่
            return r.status_code == 200 and "<fault>" not in r.text
        except: return False

    def get_downloading_size(self):
        """ดึงขนาดไฟล์ที่กำลังโหลดค้างอยู่ (Bytes ที่เหลือ)"""
        try:
            # ใช้ multicall เพื่อดึง size และ completed bytes ของไฟล์ที่กำลังทำงาน (view: started)
            xml = '''<?xml version="1.0"?>
            <methodCall>
                <methodName>d.multicall2</methodName>
                <params>
                    <param><value><string></string></value></param>
                    <param><value><string>started</string></value></param>
                    <param><value><string>d.size_bytes=</string></value></param>
                    <param><value><string>d.completed_bytes=</string></value></param>
                </params>
            </methodCall>'''
            
            r = requests.post(self.url, data=xml, auth=self.auth, headers=self.headers, verify=False, timeout=10)
            if r.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(r.text)
                total_remaining = 0
                
                # แกะค่า XML เพื่อหาผลรวมของ (Size - Completed)
                # หมายเหตุ: โครงสร้าง XML ของ rTorrent อาจต้องใช้ตัวช่วย parse ที่แม่นยำ
                # นี่คือตัวอย่างการคำนวณคร่าวๆ
                for data_node in root.findall(".//data/value/array/data/value/array"):
                    vals = [v.text for v in data_node.findall("./value")]
                    if len(vals) >= 2:
                        size = int(vals[0])
                        completed = int(vals[1])
                        total_remaining += (size - completed)
                
                return total_remaining / (1024**3) # คืนค่าเป็น GB
            return 0.0
        except:
            return 0.0
                    
    def get_active_downloads(self):
        """ดึงรายการที่กำลังโหลด โดยเปลี่ยนไปใช้ view 'main' เพื่อเลี่ยง Error 503"""
        try:
            import xmlrpc.client
            # ผสม Auth ลงใน URL
            auth_url = self.url.replace("://", f"://{self.user}:{self.pw}@")
            proxy = xmlrpc.client.ServerProxy(auth_url)

            # ดึงจาก view "main" ซึ่งเป็นมาตรฐานของ rTorrent ทุกเวอร์ชั่น
            token = ""
            # เพิ่ม d.get_complete= เพื่อเช็คว่าตัวไหนยังโหลดไม่เสร็จ
            params = ("main", "d.hash=", "d.size_bytes=", "d.complete=")
            response = proxy.d.multicall2(token, *params)

            results = []
            for t in response:
                # d.complete == 0 หมายถึงกำลังดาวน์โหลด (หรือยังโหลดไม่เสร็จ)
                if int(t[2]) == 0:
                    results.append({
                        'hash': t[0],
                        'size_bytes': int(t[1]),
                        'state': 'downloading'
                    })
            return results
        except Exception as e:
            # หากเกิด Error ให้พยายาม Login ใหม่ในรอบหน้า
            self.is_connected = False
            print(f"❌ [{self.name}] rTorrent Error: {e}")
            return []

    def add(self, content, size=None, n_cfg=None):
        try:
            # 1. เช็คว่า content มีข้อมูลจริงไหม (ถ้าโดนบล็อกจะเป็นหน้าเว็บเปล่าๆ ขนาดจะเล็กมาก)
            if len(content) < 1000:
                print(f"❌ [{self.name}] Torrent file is too small or invalid.")
                return False

            b64 = base64.b64encode(content).decode('utf-8')

            # ปรับ XML ให้เป็นมาตรฐานที่รองรับทั้ง rTorrent รุ่นเก่าและใหม่
            xml = f'''<?xml version="1.0"?>
            <methodCall>
                <methodName>load.raw_start</methodName>
                <params>
                    <param><value><string></string></value></param>
                    <param><value><base64>{b64}</base64></value></param>     
                </params>
            </methodCall>'''

            # ต้องใส่ headers เข้าไปด้วย (สำคัญมากสำหรับบาง Host)
            r = requests.post(
                self.url,
                data=xml,
                auth=self.auth,
                headers=self.headers, # ใช้ headers ที่เราตั้งไว้ใน __init__
                timeout=30,
                verify=False
            )

            if r.status_code == 200:
                # ถ้า rTorrent รับสำเร็จ มันจะตอบกลับมาเป็น XML ที่มีค่า i4 หรือ i8 เป็น 0
                return True
            else:
                print(f"❌ [{self.name}] Server returned status: {r.status_code}")
                return False
        except Exception as e:
            print(f"❌ [{self.name}] Add Error: {e}")
            return False

    def delete_torrent(self, t_hash):
        """Hard Delete: หยุดและลบข้อมูลในคำสั่งเดียว (Atomic Operation)"""
        #สิ่งที่ต้องเพิ่มใน .rtorrent.rc
        #ให้เพิ่มบรรทัดนี้ไว้ก่อนบรรทัด # -- END HERE --:
        #method.set_key = event.download.erased, delete_tied, "execute={rm,-rf,--,$d.base_path=}"
        try:
            # รวม d.stop และ d.erase เข้าเป็นก้อนเดียว
            xml = f'''<?xml version="1.0"?>
            <methodCall>
              <methodName>system.multicall</methodName>
              <params>
                <param><value><array><data>
                  <value><struct>
                    <member><name>methodName</name><value><string>d.stop</string></value></member>
                    <member><name>params</name><value><array><data><value><string>{t_hash}</string></value></data></array></value></member>
                  </struct></value>
                  <value><struct>
                    <member><name>methodName</name><value><string>d.erase</string></value></member>
                    <member><name>params</name><value><array><data><value><string>{t_hash}</string></value></data></array></value></member>
                  </struct></value>
                </data></array></value></param>
              </params>
            </methodCall>'''

            r = requests.post(self.url, data=xml, auth=self.auth, headers=self.headers, verify=False, timeout=10)
            return r.status_code == 200
        except Exception as e:
            print(f"❌ [{self.name}] Delete Error: {e}")
            return False

    def reannounce_all(self):
        if not self.is_connected and not self.login(): return False
        try:
            # ใช้ multicall2 สั่ง d.tracker_announce ทุกตัวในหน้าหลัก (main) พร้อมกัน
            xml = (
                '<?xml version="1.0"?>'
                '<methodCall>'
                '<methodName>d.multicall2</methodName>'
                '<params>'
                '<param><value><string></string></value></param>'
                '<param><value><string>main</string></value></param>'
                '<param><value><string>d.tracker_announce=</string></value></param>'
                '</params>'
                '</methodCall>'
            )
            requests.post(self.url, data=xml, auth=self.auth, headers=self.headers, timeout=15, verify=False)
            return True
        except: return False

# ========================= UPDATE TRACKER =========================

def update_trackers(node):
    """ สั่งให้ Node อัปเดตข้อมูลไปยัง Tracker """
    try:
        # สมมติว่าคุณเพิ่ม method reannounce_all ใน Class ไว้แล้วตามที่คุยกันก่อนหน้า
        if hasattr(node, 'reannounce_all'):
            if node.reannounce_all():
                print(f"  ✅ [{node.name}] Trackers re-announced.")
                return True
        else:
            # กรณีไม่ได้เพิ่ม method ใน class สามารถใช้ logic นี้แทนได้
            if isinstance(node, QbitNode):
                node.s.post(f"{node.url}/api/v2/torrents/reannounce", data={"hashes": "all"}, auth=node.auth, timeout=10)
            elif isinstance(node, RtorrentNode):
                # logic rtorrent re-announce
                pass
            print(f"  ✅ [{node.name}] Sent re-announce request.")
    except Exception as e:
        print(f"  ⚠️ [{node.name}] Update trackers failed: {e}")
    return False

# ========================= AUTO CLEAN =========================

class NodeCleaner:
    def __init__(self, node_obj, node_clean_cfg, global_clean_cfg):
        self.node = node_obj
        self.node_cfg = node_clean_cfg or {}
        self.global_cfg = global_clean_cfg or {}

    def process(self, force_emergency=False):
        """
        ระบบตรวจสอบและลบทอร์เรนต์ที่หมดอายุ
        :param force_emergency: บังคับใช้โหมดลบด่วน (ใช้เมื่อต้องการคืนพื้นที่ทันที)
        """
        node_enable = self.node_cfg.get('enable')
        global_enable = self.global_cfg.get('enable', False)

        # ตรวจสอบสิทธิ์การใช้งาน (Node Priority > Global)
        is_enabled = node_enable or global_enable
        if not is_enabled:
            return

        # เช็คสภาวะดิสก์เต็ม (Emergency) ถ้าพื้นที่เหลือน้อยกว่า 10GB หรือถูกสั่ง Force
        # โดยอ้างอิงจากค่า free_gb ของ Node นั้นๆ
        is_emergency = force_emergency or (self.node.free_gb < 10.0)
        if is_emergency:
            print(f"🚨 [EMERGENCY CLEAN] [{self.node.name}] พื้นที่วิกฤตเหลือ {self.node.free_gb:.2f}GB")

        print(f"🔍 Debug: [{self.node.name}] Starting cleanup process... (Emergency: {is_emergency})")

        try:
            removed_list = []
            if isinstance(self.node, QbitNode):
                removed_list = self._clean_qbit(is_emergency)
            elif isinstance(self.node, RtorrentNode):
                removed_list = self._clean_rtorrent(is_emergency)

            if removed_list:
                status_title = "🚨 EMERGENCY Cleanup" if is_emergency else "🧹 Cleanup Summary"
                msg = f"{status_title} [{self.node.name}]:\n" + "\n".join(removed_list)
                send_notify(msg)
        except Exception as e:
            print(f"⚠️ [{self.node.name}] Clean Error: {e}")

    def _should_remove(self, ratio, age_hours, is_emergency=False):
        """
        Logic การตัดสินใจลบไฟล์
        """
        # หากอยู่ในโหมดฉุกเฉิน จะลดเกณฑ์การลบลงครึ่งหนึ่ง (ลบง่ายขึ้น) เพื่อรีบคืนพื้นที่
        threshold_div = 2 if is_emergency else 1

        use_node_cfg = self.node_cfg.get('enable', False)
        cfg = self.node_cfg if use_node_cfg else self.global_cfg

        # ถ้าพื้นที่เป็น 0.0GB จริงๆ ให้ใช้เกณฑ์ "ล้างป่าช้า"
        if self.node.free_gb <= 0.01:
            # ลบไฟล์ที่อยู่เกิน 2 ชม. ทิ้งทันทีเพื่อกู้ชีพ Node
            if age_hours >= 2: return True

        # ดึงค่า Config (Ratio / Min Time / Max Time)
        min_ratio = (cfg.get('min_ratio', 1.0)) / threshold_div
        min_time = (cfg.get('min_time', 360) / 60) / threshold_div
        max_time = (cfg.get('max_time', 1440) / 60) / threshold_div

        # 1. ลบถ้าอยู่มานานเกิน Max Time
        if age_hours >= max_time:
            return True

        # 2. ลบถ้าอยู่เกิน Min Time และ Ratio ถึงเป้าหมาย
        if age_hours >= min_time and ratio >= min_ratio:
            return True

        return False

    def _clean_qbit(self, is_emergency):
        res = []
        # ดึงข้อมูลจาก qBittorrent Web API
        r = self.node.s.get(f"{self.node.url}/api/v2/torrents/info", auth=self.node.auth, verify=False, timeout=15)
        if r.status_code != 200: return []

        torrents = r.json()
        now = time.time()
        for t in torrents:
            # ข้ามถ้ายังโหลดไม่เสร็จ
            if t.get('progress', 0) < 1: continue

            completion_on = t.get('completion_on', 0)
            if completion_on <= 0: continue

            age_hours = (now - completion_on) / 3600
            ratio = t.get('ratio', 0)

            if self._should_remove(ratio, age_hours, is_emergency):
                if self.node.delete_torrent(t['hash']):
                    line = f"  🗑️ {t['name'][:30]} (R:{ratio:.2f}, {age_hours:.1f}h)"
                    print(line); res.append(line)
        return res

    def _clean_rtorrent(self, is_emergency):
        res = []
        # XML-RPC สำหรับ rTorrent multicall
        xml = (
            '<?xml version="1.0"?><methodCall><methodName>d.multicall2</methodName>'
            '<params><param><value><string></string></value></param>'
            '<param><value><string>main</string></value></param>'
            '<param><value><string>d.hash=</string></value></param>'
            '<param><value><string>d.ratio=</string></value></param>'
            '<param><value><string>d.timestamp.finished=</string></value></param>'
            '<param><value><string>d.name=</string></value></param></params></methodCall>'
        )

        try:
            r = requests.post(self.node.url, data=xml, auth=self.node.auth, verify=False, timeout=15)
            if r.status_code != 200: return []

            soup = BeautifulSoup(r.text, "xml")
            response = soup.find('methodResponse')
            if not response: return []

            torrent_entries = response.find_all('data')
            now = time.time()

            for entry in torrent_entries:
                vals = [v.get_text().strip() for v in entry.find_all('value', recursive=False)]
                if len(vals) < 4: continue

                t_hash, t_ratio_raw, t_finish, t_name = vals[0], vals[1], vals[2], vals[3]

                if not t_finish.isdigit() or int(t_finish) <= 0: continue

                ratio = int(t_ratio_raw) / 1000 if t_ratio_raw.isdigit() else 0
                age_hours = (now - int(t_finish)) / 3600

                if self._should_remove(ratio, age_hours, is_emergency):
                    if self.node.delete_torrent(t_hash):
                        line = f"  🗑️ {t_name[:30]} (R:{ratio:.2f}, {age_hours:.1f}h)"
                        print(line); res.append(line)

        except Exception as e:
            print(f"⚠️ [{self.node.name}] rTorrent Clean Error: {str(e)}")
        return res

# ========================= Smart Reclaim Space =========================

def smart_reclaim_process(node, required_gb):
    """
    เวอร์ชันแก้ไข: รองรับทั้ง QbitNode และ RtorrentNode โดยใช้ Method ภายในคลาส
    """
    try:
        # 1. ดึงข้อมูลงานที่โหลดเสร็จแล้วผ่าน Method ของ Node
        torrents = node.get_all_torrents_info()
        if not torrents:
            print(f"⚠️ [{node.name}] ไม่มีงานที่โหลดเสร็จแล้วให้ลบ")
            return False

        # 2. จัดลำดับ: ลบตัวที่ Ratio สูงสุดก่อน
        torrents.sort(key=lambda x: x.get('ratio', 0), reverse=True)

        target_free = required_gb + 15.0 # Buffer 15GB สำหรับช่วง Santa 100%

        for t in torrents:
            # อัปเดตพื้นที่ล่าสุดของ Node
            node.refresh_status()
            if node.free_gb >= target_free:
                print(f"✅ [{node.name}] พื้นที่เพียงพอแล้ว: {node.free_gb:.2f} GB")
                return True

            print(f"🧹 [{node.name}] กำลังลบ: {t['name'][:30]} (Ratio: {t['ratio']:.2f})")

            # เรียกใช้ delete_torrent ของ Node (ซึ่งรองรับทั้ง qBit และ rTorrent)
            node.delete_torrent(t['hash'])

            # 3. เผื่อเวลาให้ Disk คืน Quota (สำคัญมากสำหรับ Seedbox)
            time.sleep(5)

        node.refresh_status()
        return node.free_gb >= target_free

    except Exception as e:
        print(f"❌ Reclaim Error on {node.name}: {str(e)}")
        return False

# ========================= BEARBIT STATUS =========================

def save_hourly_snapshot(current_data):
    try:
        # 1. โหลดข้อมูลเดิมด้วยวิธีที่ปลอดภัย
        if os.path.exists(STATS_HISTORY_FILE):
            with open(STATS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                try:
                    history = json.load(f)
                except json.JSONDecodeError: # กันเหนียวถ้าไฟล์พังหรือว่างเปล่า
                    history = {}
        else:
            history = {}

        now = get_now()
        # ใช้ Key แบบรายชั่วโมง (เช่น "2026-04-29 10:00")
        # เพื่อให้สถิติ 1 ชั่วโมงมีแค่ 1 Snapshopt ที่เป็นค่าล่าสุด
        timestamp_key = now.strftime("%Y-%m-%d %H:00")
        
        history[timestamp_key] = {
            'username': current_data.get('username', 'N/A'),
            'ratio': current_data.get('ratio', 0),
            'up': current_data.get('up', 0),
            'dl': current_data.get('dl', 0),
            'bonus': current_data.get('bonus', 0),
            'raw_time': now.strftime("%Y-%m-%d %H:%M:%S")
        }

        # 2. เก็บย้อนหลัง 31 วัน (744 จุดข้อมูล)
        if len(history) > 744:
            # เก็บเฉพาะคีย์ที่ใหม่ที่สุด 744 อันดับ
            sorted_keys = sorted(history.keys())[-744:]
            history = {k: history[k] for k in sorted_keys}

        # 3. บันทึกไฟล์แบบ Atomically (เขียนไฟล์ใหม่แล้วค่อยเปลี่ยนชื่อ เพื่อกันไฟล์พังตอนไฟดับ/เน็ตหลุด)
        temp_file = STATS_HISTORY_FILE + ".tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=4)
        os.replace(temp_file, STATS_HISTORY_FILE)

    except Exception as e:
        print(f"❌ Log History Error: {e}")

def get_stats_diff(current_data):
    """เปรียบเทียบค่าปัจจุบันกับค่าที่บันทึกไว้"""
    diff_msg = ""
    if os.path.exists(STATS_CACHE_FILE):
        try:
            with open(STATS_CACHE_FILE, 'r', encoding='utf-8') as f:
                old_data = json.load(f)

            # --- ส่วนคำนวณเหมือนเดิมที่คุณเขียนไว้ ---
            def calc_num_diff(curr, old, precision=3):
                c = float(str(curr).replace(',', ''))
                o = float(str(old).replace(',', ''))
                res = c - o
                return f"+{res:.{precision}f}" if res > 0 else (f"{res:.{precision}f}" if res < 0 else "0")

            def calc_size_diff(curr_str, old_str):
                curr_gb = parse_size(curr_str)
                old_gb = parse_size(old_str)
                diff_gb = curr_gb - old_gb
                if diff_gb == 0: return "0"
                if abs(diff_gb) >= 1024:
                    val = diff_gb/1024
                    return f"+{val:.2f} TB" if val > 0 else f"{val:.2f} TB"
                return f"+{diff_gb:.2f} GB" if diff_gb > 0 else f"{diff_gb:.2f} GB"

            up_diff = calc_size_diff(current_data['up'], old_data['up'])
            dl_diff = calc_size_diff(current_data['dl'], old_data['dl'])
            b_diff = calc_num_diff(current_data['bonus'], old_data['bonus'], 1)

            # --- จุดที่ปรับแต่ง: ทำให้ Changes กระชับขึ้น ---
            changes = []
            if up_diff != "0": changes.append(f"Up: ({up_diff})")
            if dl_diff != "0": changes.append(f"Dl: ({dl_diff})")
            if b_diff != "0": changes.append(f"💰 {b_diff}") # โบนัสอาจจะเก็บไว้ดูง่ายๆ

            if changes:
                # ส่งคืนแค่ Changes: พร้อมข้อมูล (ไม่มี \n)
                diff_msg = "<b>Changes:</b> " + " | ".join(changes)
        except Exception as e:
            print(f"Error reading cache: {e}")

    # บันทึกค่าปัจจุบันทับเสมอ
    with open(STATS_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(current_data, f)

    return diff_msg

def check_item_urgency(exp_time_str):
    try:
        if exp_time_str == "N/A": return False
        now = datetime.now()

        # ถ้ารูปแบบเป็นวันที่ยาว (2026-04-29 20:30:15)
        if "-" in exp_time_str:
            exp_dt = datetime.strptime(exp_time_str, "%Y-%m-%d %H:%M:%S")
        else:
            # ถ้ารูปแบบเป็นแค่เวลา (20:30:15)
            exp_dt = datetime.strptime(exp_time_str, "%H:%M:%S").replace(
                year=now.year, month=now.month, day=now.day
            )

        diff = (exp_dt - now).total_seconds() / 60
        return 0 < diff <= 30
    except:
        return False

def get_bearbit_stats(page):
    try:
        global CFG
        # --- 1. เข้าหน้าโปรไฟล์ ---
        content = page.content()
        soup = BeautifulSoup(content, 'html.parser')
        user_tag = soup.find("a", href=re.compile(r"userdetails\.php\?id=\d+"))

        if user_tag:
            profile_url = "https://bearbit.org/" + user_tag['href']
            page.goto(profile_url, wait_until="networkidle")
            soup = BeautifulSoup(page.content(), 'html.parser')
            username = user_tag.get_text(strip=True)
        else:
            username = "Unknown"

        # --- 2. เช็คไอเทมและเวลาหมดอายุ (เวอร์ชันแก้ไขเสถียรภาพ) ---
        active_item = "NONE"
        raw_exp = "N/A"
        display_exp = "N/A"

        # เจาะจงหาแถวที่มีข้อมูลไอเทม เพื่อไม่ให้ไปดึง "เวลาสมัครสมาชิก" มาผิด
        item_row = soup.find("td", string=re.compile(r"Item Status|หมดอายุ Item"))
        if item_row:
            # ดึงข้อมูลจากช่อง <td> ถัดไป
            full_text = item_row.find_next_sibling("td").get_text(strip=True)

            # ตรวจสอบประเภทไอเทม
            if any(x in full_text for x in ["ซานตาคลอส", "100%"]):
                active_item = "FREELOAD_100"
            elif any(x in full_text for x in ["ตุ๊กตาซานต้า", "50%"]):
                active_item = "FREELOAD_50"
            elif any(x in full_text for x in ["หยินหยาง", "15%"]):
                active_item = "FREELOAD_15"
            elif any(x in full_text for x in ["แหวนครองพิภพ", "10%"]):
                active_item = "FREELOAD_10"

            # Regex แบบยืดหยุ่นสูง:
            # \d{2}-\d{2}-\d{4} คือ วัน-เดือน-ปี
            # \s+ คือ ช่องว่าง (รองรับทั้ง Space ปกติ และตัวอักษรพิเศษ)
            # \d{2}:\d{2}:\d{2} คือ ชม:นาที:วินาที
            exp_match = re.search(r"(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}:\d{2})", full_text)
            if exp_match:
                raw_exp = exp_match.group(1)
                parts = re.split(r'\s+', raw_exp.strip())
                if len(parts) >= 2:
                    display_exp = f"{parts[0]} / {parts[1][:5]}"

        # จัดการแสดงผล Item
        if active_item != "NONE":
            item_display = f"<b>{active_item}</b> ({display_exp})"
            # แจ้งเตือนถ้าใกล้หมดเวลา (เช็คจาก raw_exp ที่ดึงมาใหม่)
            urgency_alert = "⚠️ <b>ใกล้หมดเวลา!</b>\n" if check_item_urgency(raw_exp) else ""
        else:
            item_display = "NONE"
            urgency_alert = ""

        update_bot_config(active_item)

        # --- 3. ดึงสถิติตัวเลข ---
        text = soup.get_text(separator=" ")
        ratio = re.search(r"Ratio:\s*([\d\.,]+)", text)
        up = re.search(r"Uploaded:\s*([\d\.,]+\s*[KMGTP]B)", text)
        dl = re.search(r"Downloaded:\s*([\d\.,]+\s*[KMGTP]B)", text)
        bonus = re.search(r"Bonus:\s*([\d\.,]+)", text)

        if ratio and up and dl:
            curr_data = {
                'username': username,
                'ratio': ratio.group(1),
                'up': up.group(1),
                'dl': dl.group(1),
                'bonus': bonus.group(1) if bonus else "0"
            }
            diff_text = get_stats_diff(curr_data)

            # บันทึก Snapshot ลงไฟล์ JSON (ใช้คีย์สั้น 'up', 'dl' ตามที่คุณระบุ)
            numeric_data = {
                'username': username,
                'ratio': float(curr_data['ratio'].replace(',', '')),
                'up': parse_size(curr_data['up']),
                'dl': parse_size(curr_data['dl']),
                'bonus': float(curr_data['bonus'].replace(',', ''))
            }
            save_hourly_snapshot(numeric_data)

            # จัดรูปแบบข้อความส่ง Telegram
            stats_msg = (
                f"👤 <b>{username}</b> | Ratio: {ratio.group(1)}\n"
                f"📤 Up: {up.group(1)} | 📥 Dl: {dl.group(1)}\n"
                f"💰 Bonus: {curr_data['bonus']} | 🎁 Item: {item_display}\n"
                f"{urgency_alert + '\n' if urgency_alert else ''}"
                f"{'🔄 ' + diff_text if diff_text else ''}"
            )
            return stats_msg

        return "⚠️ ไม่สามารถดึงสถิติได้"

    except Exception as e:
        # หากเกิด Error จะแจ้งรายละเอียดเพื่อช่วย Debug
        return f"⚠️ Stats Error: {str(e)}"

def update_bot_config(active_item):
    global CFG
    if not CFG or 'SETTING' not in CFG: return

    discounts = {
        "FREELOAD_100": 100,
        "FREELOAD_50": 50,
        "FREELOAD_30": 30,
        "FREELOAD_15": 15,
        "FREELOAD_10": 10
    }

    current_discount = discounts.get(active_item, 0)
    CFG['SETTING']['CURRENT_DISCOUNT'] = current_discount

    if current_discount == 100:
        # โหมดฟรี 100%: ไม่ต้องสนหน้าเว็บ ไม่ต้องสน Pending เพราะเราฟรีแน่นอน
        CFG['SETTING']['FREELOAD_ENABLE'] = True
        CFG['SETTING']['MIN_FREE_PERCENT'] = 0
        CFG['SETTING']['EXCLUDE_WEB_FREE'] = False # ไม่ต้องเลี่ยงไฟล์ฟรี เพราะยังไงเราก็ฟรี
        print("🚀 [FREE 100% MODE]: กวาดทุกไฟล์ไม่สนหน้าเว็บ (เน้นเก็บยอดอัปโหลด)")

    elif current_discount > 0:
        # โหมดมีส่วนลด (เช่น 50%): ต้องใช้ลอจิกคัดกรองความคุ้มค่า
        CFG['SETTING']['FREELOAD_ENABLE'] = True
        CFG['SETTING']['MIN_FREE_PERCENT'] = 0
        CFG['SETTING']['EXCLUDE_WEB_FREE'] = True
        print(f"⚠️ [DISCOUNT {current_discount}% MODE]: เน้นไฟล์ที่ใช้ไอเทมแล้วคุ้มกว่าหน้าเว็บ")

    else:
        # โหมดปกติ: ไอเทมหมดอายุ
        try:
            with open('config.json', 'r', encoding='utf-8') as f:
                new_cfg = json.load(f)
                CFG['SETTING'].update(new_cfg.get('SETTING', {}))

            # --- เสริมกำแพงป้องกัน ---
            CFG['SETTING']['CURRENT_DISCOUNT'] = 0

            print("🛡️ [NORMAL MODE]: กลับสู่โหมดปกติ")
        except Exception as e:
            # กรณีโหลดไฟล์ไม่สำเร็จ ให้ใช้ค่า Hard-coded ที่ปลอดภัยที่สุด
            CFG['SETTING']['CURRENT_DISCOUNT'] = 0
            print(f"❌ Error reloading config: {e} | Switching to Emergency Safety Mode")

# ========================= Smart Node Controller =========================

def calculate_task_weight(size_gb):
    """คำนวณน้ำหนักไฟล์: เล็ก=1, กลาง=2, ใหญ่=3"""
    if size_gb < 8: return 1
    elif size_gb < 20: return 2
    return 3

def get_node_dynamic_cap(node, disk_type):
    """คำนวณ Capacity อัตโนมัติ พร้อมระบบ Reset Connection เมื่อ API ค้าง"""
    # ปรับ Base Caps: HDD ให้รับงานเล็กๆ ได้มากขึ้นเพื่อปั๊มโหวต
    base_caps = {
        'NVME': 15,    # NVMe แรงมาก รับน้ำหนักได้เยอะ (ประมาณ 5 งานใหญ่)
        'SSD': 10,     # SSD ทั่วไป
        'HYBRID': 8,   # SSD/NVME Cache + HDD เพื่อให้รับงานใหญ่ได้ 6 งาน
        'HDD': 4       # HDD ปกติขยับขึ้นมานิดนึง
    }
    base = base_caps.get(disk_type, 3)
    start = time.time()
    try:
        # ลองดึง status เพื่อเช็คว่า API ยังมีชีวิตอยู่ไหม
        node.refresh_status()
        latency = (time.time() - start) * 1000

        # ปรับตัวหารความหน่วงตามประเภทดิสก์ (HDD จะทนความหน่วงได้มากกว่า)
        div = 100 if disk_type == 'HDD' else 50
        proxy_wait = max(0, (latency - 200) / div)

    except Exception as e:
        # จุดตาย: ถ้า API พัง ให้ Reset สถานะทันทีเพื่อให้รอบหน้า Login ใหม่
        node.is_connected = False
        proxy_wait = 20
        print(f"⚠️ [{node.name}] API Error: {e} | Connection Reset triggered.")

    # ปรับค่าการลดทอน (Reduction)
    reductions = {
        'NVME': 10,    # ให้โอกาส NVMe ทำงานหนักได้นานกว่า
        'HYBRID': 8,   # Hybrid ให้ความเสถียรปานกลาง
        'SSD': 6,
        'HDD': 4       # HDD ต้องระวัง ถ้าเริ่มหน่วงให้รีบลด Cap ทันทีป้องกัน Disk ค้าง
    }

    # --- [ปรับปรุง] ระบบตรวจสอบโควตาพื้นที่คงเหลือ (Dynamic Space Scaler - 10% Reserve) ---
    quota = node.quota_gb if node.quota_gb > 0 else 1000  # ถ้าไม่มีโควตาให้ Assume ที่ 1TB
    free_gb = node.free_gb

    # คำนวณเปอร์เซ็นต์พื้นที่ว่างที่เหลืออยู่เมื่อเทียบกับโควตา
    free_percent = (free_gb / quota) * 100

    # ระบบค่อยๆ ลดระดับการรับงาน (Step-down Scaling)
    if free_percent > 85:          # โซนว่างมาก (เช่น Swizzin ปัจจุบัน)
        space_factor = 5.0         # อัดฉีดเต็มสูบเพื่อรีดประสิทธิภาพ
    elif free_percent > 70:        # ลดระดับที่ 1 (-15%)
        space_factor = 4.0
    elif free_percent > 55:        # ลดระดับที่ 2 (-15%)
        space_factor = 3.0
    elif free_percent > 40:        # ลดระดับที่ 3 (-15%)
        space_factor = 2.0
    elif free_percent > 25:        # ลดระดับที่ 4 (-15%)
        space_factor = 1.0         # เริ่มกลับสู่โหมดทำงานปกติ
    elif free_percent > 10:        # โซนเตรียมหยุด (เหลือ 10-25%)
        space_factor = 0.5         # รับเฉพาะงานเล็กประคองตัว
    else:                          # ต่ำกว่า 10% (Safety Zone)
        space_factor = 0.0         # ปิดการรับงานทันทีเพื่อรักษาพื้นที่สำรอง
        print(f"🛑 [{node.name}] Safety Stop: Reserved 10% reached. All new tasks blocked.")

    # คำนวณ Cap พื้นฐานจาก Latency ก่อน
    reduction = reductions.get(disk_type, 6)
    latency_cap = int(base / (1 + (proxy_wait / reduction)))

    # --- [Final Cap] รวมปัจจัยความหน่วง + พื้นที่คงเหลือ ---
    # ใช้ค่าน้ำหนักงานรวม (Weight Cap) แทนจำนวนไฟล์
    dynamic_weight_cap = max(2, int(latency_cap * space_factor))

    return dynamic_weight_cap, proxy_wait

def get_node_current_weight(node):
    """คำนวณน้ำหนักงานปัจจุบันที่กำลัง 'เขียนดิสก์' (Downloading)"""
    active_torrents = node.get_active_downloads() # ดึงรายการที่สถานะ Downloading/Checking
    total_weight = 0
    for t in active_torrents:
        size_gb = t.get('size_bytes', 0) / (1024**3)
        # น้ำหนักงาน: เล็ก=1 (<8GB), กลาง=2 (8-20GB), ใหญ่=3 (>20GB)
        total_weight += 1 if size_gb < 8 else (2 if size_gb < 20 else 3)
    return total_weight

# ========================= AUTO VOTE =========================

def auto_vote_snatched(page):
    try:
        max_p = 5
        print(f"🗳️ Vote system started ({max_p} pages)")
        page.goto("https://bearbit.org/snatchdown.php", wait_until="networkidle")
        for p_idx in range(1, max_p + 1):
            vote_targets = page.locator('img[title="ยอดเยี่ยม"], img[src*="v5.1.1.png"]')
            count = vote_targets.count()
            if count > 0:
                for i in range(count):
                    try: vote_targets.first.click(); time.sleep(random.uniform(1.0, 1.5))
                    except: continue
            next_btn = page.locator('img[src*="nextpage.gif"]').first
            if next_btn.is_visible() and p_idx < max_p: next_btn.click(); time.sleep(2)
            else: break
        send_notify("🗳️ Vote session completed.")
    except Exception as e: print(f"❌ Vote Error: {e}")

# ========================= MAIN FUNCTIONS =========================

def generate_main_status(config):
    SET = config.get('SETTING', {})
    
    # ดึงค่าและกำหนดค่าเริ่มต้น (Default) ให้ตรงกับที่คุณระบุ
    min_gb = SET.get('MIN_SIZE_GB', 5.0)
    max_gb = SET.get('MAX_SIZE_GB', 150.0)
    is_freeload = SET.get('FREELOAD_ENABLE', True)
    min_percent = SET.get('MIN_FREE_PERCENT', 0) # ใช้ชื่อ Key ให้ตรงกับใน loop สแกน

    # จัดรูปแบบข้อความ
    status_text = "เปิด" if is_freeload else "ปิด"
    # แสดง % เฉพาะตอนเปิดเท่านั้น
    freeload_info = f" (ขั้นต่ำ: {min_percent}%)" if is_freeload else ""
    
    # คืนค่าบรรทัดเงื่อนไขตาม Format ที่ต้องการ
    return f"⚙️ เงื่อนไข: ขนาด {min_gb:.1f}-{max_gb:.1f}GB | ฟรีโหลด {status_text}{freeload_info}"

def main():
    startup_msg = "🚀 BearBit Auto-Pilot : Started"
    print(startup_msg); send_notify(startup_msg)
    
    while True:
        try:
            global CFG
            CFG = load_full_config()
            SET = CFG.get('SETTING', {})
            global_clean = CFG.get('GLOBAL_CLEAN', {})
            seen_ids = load_data(SEEN_FILE)
            seen_hashes = load_data(HASH_SEEN_FILE)
            active_nodes = []
            node_status_buffer = []

            # 1. Node Section (Checking & Cleanup & Update Trackers)
            print("\n🔌 NODE STATUS CHECKING...")
            for n_cfg in CFG['NODES']:
                if not n_cfg.get('enable'): continue
                
                # สร้าง Object ตามประเภทของ Node
                node = RtorrentNode(n_cfg) if n_cfg.get("type") == "rtorrent" else QbitNode(n_cfg)

                if node.login():
                    # 1. ต้อง refresh ก่อนเพื่อให้ NodeCleaner รู้ค่าพื้นที่ที่แท้จริง
                    node.refresh_status()
                    pre_free = node.free_gb  # เก็บค่าพื้นที่ "ก่อนลบ"

                    # 2. เริ่ม Cleanup (ส่งแรงกระตุ้นให้โหมด Emergency ทำงาน)
                    # ตรวจสอบให้แน่ใจว่าได้อัปเดตคลาส NodeCleaner ให้รับค่า is_emergency แล้ว
                    NodeCleaner(node, n_cfg.get('clean_settings', {}), global_clean).process()

                    # 3. ให้เวลาระบบไฟล์คืนพื้นที่ และอัปเดต Tracker
                    time.sleep(2)
                    node.reannounce_all()

                    # 4. refresh อีกครั้งเพื่อดูค่าพื้นที่ "หลังลบ"
                    node.refresh_status()

                    # 5. คำนวณและแสดงผลพื้นที่ที่กู้คืนมาได้
                    gained = node.free_gb - pre_free
                    if gained > 0.01:
                        print(f"✨ [{node.name}] Cleaned up: {gained:.2f} GB recovered!")

                    active_nodes.append((node, n_cfg))
                    icon = "🟢"
                else: icon = "❌"
                line = f"{icon} [{node.name}] FREE {getattr(node,'free_gb',0):.1f}GB | {getattr(node,'stat_msg','N/A')}"
                print(line); node_status_buffer.append(line)
                update_trackers(node)

            if active_nodes:
                print("⏳ Waiting 5s for trackers to sync with BearBit...")
                time.sleep(5)

            if node_status_buffer:
                send_notify("🔌 <b>Node Status Report</b>\n" + "\n".join(node_status_buffer))

            # 2. Browser Section
            with sync_playwright() as p:
                browser, browser_path = launch_any_browser(p)
                context = browser.new_context(user_agent="Mozilla/5.0...")
                page = context.new_page()
                
                def safe_goto(url, retries=3):
                    for i in range(retries):
                        try:
                            if page.is_closed(): return False
                            # เปลี่ยนเป็น networkidle เพื่อความชัวร์ว่าโหลดปุ่มต่างๆ มาครบ
                            page.goto(url, wait_until="networkidle", timeout=60000)
                            return True
                        except Exception as e:
                            print(f"⚠️ Retry {i+1}: {e}")
                            time.sleep(5)
                    return False

                # --- Login ---
                if safe_goto("https://bearbit.org/login.php"):
                    page.fill('input[name="username"]', CFG['BEARBIT']['username'])
                    page.fill('input[name="password"]', CFG['BEARBIT']['password'])
                    page.click('input[type="submit"]')
                    time.sleep(3)

                    if "logout.php" in page.content():
                        print("🔑 Login Success")
                        stats_report = get_bearbit_stats(page)
                        print(f"\n{stats_report}")
                        send_notify(f"📊 <b>BearBit Status Report</b>\n{stats_report}")
    
                        auto_vote_snatched(page) # โหวตครั้งเดียวตอนเริ่มรอบ
                        
                        
                        dl_session = requests.Session()
                        dl_session.cookies.update({c['name']: c['value'] for c in context.cookies()})

                        # --- วนลูปสแกนแต่ละโซน (Target URLs) ---
                        for target_item in CFG['BEARBIT'].get('target_urls', []):
                            if page.is_closed(): break 

                            # 1. เตรียมข้อมูลโซน
                            if isinstance(target_item, dict):
                                if not target_item.get('enable', True): continue
                                target_url = target_item.get('url')
                                display_zone = target_item.get('name', "Zone")
                            else:
                                target_url, display_zone = target_item, "Zone"

                            print(f"\n🌐 Scanning: [{display_zone}]")

                            status_line = generate_main_status(CFG) 
                            print(status_line)                        
                            
                            if not safe_goto(target_url): continue
                            
                            soup = BeautifulSoup(page.content(), "html.parser")
                            added_in_zone = [] # เก็บ msg รายการที่เพิ่มสำเร็จ
                            count_skip = 0    # นับจำนวนที่ข้าม
                        
                            # ดึงรายการ Torrent
                            all_details = soup.find_all("a", href=re.compile(r"details(new)?\.php\?id=\d+"))
                            rows = []
                            for a in all_details:
                                # เช็คว่าข้อความในลิงก์ยาวพอไหม (ชื่อไฟล์)
                                if len(a.get_text(strip=True)) > 5:
                                    parent_tr = a.find_parent("tr")
                                    if parent_tr and parent_tr not in rows:
                                        rows.append(parent_tr)
                            # --- วนลูปรายไฟล์ในโซน ---
                            for row in rows:
                                link_tag = row.find("a", href=re.compile(r"details\.php\?id=\d+"))
                                dl_link_tag = row.find("a", href=re.compile(r"download(new)?\.php\?id=\d+"))
                                if not dl_link_tag or not link_tag: continue
                            
                                t_id = re.search(r'id=(\d+)', dl_link_tag.get('href', '')).group(1)
                                t_name = re.sub(r'(Auto Sticky:|Sticky:|HOT Torrents|\[FREE\]|\[HOT\]|\n|\t)', '', link_tag.get_text()).strip()
                                t_size_gb = parse_size(row.get_text(separator=" "))

                                print(f"  🔍 Checking: {t_name[:50]}... (ID: {t_id})")

                                # ตรวจสอบเงื่อนไข Download/Free และพิมพ์เหตุผลถ้าข้าม
                                if not ("download" in str(row).lower() or "free" in str(row).lower()):
                                    print(f"      ❌ ข้าม: ไม่พบสถานะ Free หรือปุ่ม Download")
                                    count_skip += 1
                                    continue

                                # เช็คเงื่อนไขต่างๆ (Seen, Size, Free)
                                # --- [1. เช็คพื้นฐานหน้าแรก] ---
                                if t_id in seen_ids:
                                    print(f"      ❌ ข้าม: เคยเพิ่มไปแล้ว"); count_skip += 1; continue

                                if not (SET.get('MIN_SIZE_GB', 0) <= t_size_gb <= SET.get('MAX_SIZE_GB', 999)):
                                    print(f"      ❌ ข้าม: ขนาด {t_size_gb:.2f}GB ไม่ตรงเงื่อนไข"); count_skip += 1; continue

                                free_p = check_freeload_status(row)

                                # --- [2. ลอจิกคัดกรองความคุ้มค่าไอเทม] ---
                                current_item_discount = SET.get('CURRENT_DISCOUNT', 0)

                                # กรณีหน้าแรกฟรีโหลดต่ำกว่าเกณฑ์ที่ตั้งไว้
                                if SET.get('FREELOAD_ENABLE') and free_p < SET.get('MIN_FREE_PERCENT', 0):
                                    # ถ้าเราไม่มีไอเทมลดเลย (discount = 0) และหน้าแรกก็ไม่ฟรี บอทควรข้ามทันที ไม่ต้องเช็ค Details ให้เสียเวลา
                                    if current_item_discount == 0:
                                        print(f"      ❌ ข้าม: ฟรีโหลด {free_p}% ต่ำกว่ากำหนด และไม่มีไอเทมช่วยลด"); count_skip += 1; continue

                                # เช็คความคุ้มค่าเทียบกับหน้าเว็บ
                                if SET.get('EXCLUDE_WEB_FREE') and current_item_discount > 0:
                                    if free_p == 100:
                                        print(f"      ⚠️ ข้าม: หน้าเว็บฟรี 100% อยู่แล้ว"); count_skip += 1; continue
                                    if free_p >= current_item_discount:
                                        print(f"      ⚠️ ข้าม: หน้าเว็บฟรี {free_p}% คุ้มกว่า/เท่ากับไอเทมเรา"); count_skip += 1; continue

                                # --- [3. ตรวจสอบ Pending (หน้าลึก)] ---
                                # เช็คเฉพาะกรณีที่เว็บยังไม่ฟรี 100% เท่านั้น
                                if free_p < 100:
                                    time.sleep(random.uniform(0.8, 1.5))
                                    print(f"      🔍 ตรวจสอบ Pending ที่หน้ารายละเอียด ID: {t_id}")
                                    if check_pending_status(dl_session, "https://bearbit.org", t_id):
                                        print(f"      ⏳ ข้าม: พบสถานะ [รออนุมัติฟรี]... รอโหลดฟรี 100% รอบหน้า")
                                        count_skip += 1; continue

                                # --- [4. ผ่านทุกด่าน: สั่งลุย] ---
                                if current_item_discount > 0:
                                    # [โหมดมีไอเทม] (เช่น ซานต้า 50%)
                                    if free_p >= current_item_discount:
                                        print(f"      ⚠️ ข้าม: หน้าเว็บ {free_p}% คุ้มกว่าไอเทม ({current_item_discount}%)")
                                        count_skip += 1; continue
                                    is_use_item = True
                                else:
                                    # [โหมดปกติ - ไม่มีไอเทม]
                                    min_free = SET.get('MIN_FREE_PERCENT', 0)

                                    if free_p < min_free:
                                        print(f"      ❌ ข้าม: ฟรี {free_p}% ต่ำกว่าเกณฑ์ที่ตั้งไว้ ({min_free}%)")
                                        count_skip += 1; continue

                                    is_use_item = False

                                # ตอนสั่งลุย จะได้ค่าที่ถูกต้อง
                                print(f"      ✅ ลุย: หน้าเว็บฟรี {free_p}% (สิทธิ์: {'ไอเทม' if is_use_item else 'หน้าเว็บ'})")

                                r_dl = dl_session.get(f"https://bearbit.org/{dl_link_tag['href'].lstrip('/')}")
                                if r_dl.status_code == 200:
                                    t_hash = extract_info_hash(r_dl.content)
                                    if t_hash and t_hash in seen_hashes:
                                        print(f"      ❌ ข้าม: Hash ซ้ำในระบบ"); seen_ids.add(t_id); count_skip += 1; continue
                                
                                    is_already_in_node = False
                                    for node_obj, _ in active_nodes:
                                        if node_obj.is_torrent_exists(t_hash):
                                            print(f"      ❌ ข้าม: พบไฟล์ใน {node_obj.name} แล้ว (Manual Add Detection)")
                                            is_already_in_node = True
                                            break

                                    if is_already_in_node:
                                        # บันทึกลงประวัติบอทด้วยเลย จะได้ไม่ต้องเช็ค Node ในรอบหน้า
                                        seen_ids.add(t_id)
                                        if t_hash: seen_hashes.add(t_hash)
                                        count_skip += 1
                                        continue

                                    # กดขอบคุณ
                                    page.evaluate(f"sndReq('action=say_thanks&id={t_id}', 'saythanks')")
                                
                                    # --- [ส่วนเลือก Node และสั่งดาวน์โหลด] ---
                                    active_nodes.sort(key=lambda x: x[0].free_gb, reverse=True)

                                    success_node = None # ใช้มาร์คว่าแอดไฟล์สำเร็จหรือยัง
                                    task_weight = calculate_task_weight(t_size_gb)

                                    for node_obj, n_cfg in active_nodes:
                                        d_type = n_cfg.get('disk_type', 'HDD')
                                        dynamic_max_cap, p_wait = get_node_dynamic_cap(node_obj, d_type)
                                        current_load = get_node_current_weight(node_obj)

                                        print(f"📡 Check [{node_obj.name}]: Load {current_load}/{dynamic_max_cap} (Wait: {p_wait:.1f})")

                                        # 1. เช็ค Capacity
                                        if (current_load + task_weight) > dynamic_max_cap:
                                            print(f"⏳ [Queue Full] {node_obj.name} ลอง Node ถัดไป")
                                            continue

                                        # 2. เช็คพื้นที่สุทธิ
                                        effective_free_gb = node_obj.free_gb - node_obj.get_downloading_size()
                                        if effective_free_gb < (t_size_gb + 15.0):
                                            print(f"🧹 พื้นที่น้อยไป... พยายาม Reclaim")
                                            smart_reclaim_process(node_obj, t_size_gb)
                                            node_obj.refresh_status() # อัปเดตหลังลบ

                                            if node_obj.free_gb < (t_size_gb + 2.0):
                                                print(f"❌ พื้นที่ยังไม่พอ... ลอง Node ถัดไป")
                                                continue

                                        # ✅ 3. ดำเนินการ Add ไฟล์ทันทีที่เจอ Node ที่เหมาะสม
                                        try:
                                            if node_obj.add(r_dl.content):
                                                success_msg = f"📥 [Success] {node_obj.name} | {t_size_gb:.1f}GB | {t_name[:40]}"
                                                print(success_msg)

                                                # จัดการจองพื้นที่และบันทึกประวัติ
                                                booking_size = t_size_gb + 0.1
                                                node_obj.free_gb = max(0.0, node_obj.free_gb - booking_size)
                                                node_obj.stat_msg = f"Used: (Updating...) | Avail: {node_obj.free_gb:.1f}GB"

                                                added_in_zone.append(success_msg)
                                                seen_ids.add(t_id)
                                                if t_hash: seen_hashes.add(t_hash)

                                                success_node = node_obj
                                                break
                                            else:
                                                # กรณี API ตอบกลับมาเป็น False (เช่น ดิสก์ในโปรแกรมเต็ม หรือไฟล์ซ้ำ)
                                                print(f"⚠️ [API Reject] {node_obj.name} ปฏิเสธงาน (Disk Full/Dup)")
                                        except Exception as e:
                                            # 🚨 จุดสำคัญ: จะโชว์ว่า Password ผิด, Timeout หรือ Server Down
                                            print(f"❌ [Connect Error] {node_obj.name}: {str(e)}")

                                if len(added_in_zone) >= SET.get('MAX_NEW_PER_ZONE', 5): 
                                    print(f"  ⚠️ ครบโควตา {len(added_in_zone)} ไฟล์แล้ว")
                                    break

                            # ======================================================
                            # 📊 สรุปหลังจบแต่ละโซน (อยู่นอก Row loop แต่อยู่ใน Zone loop)
                            # ======================================================
                            if len(added_in_zone) > 0 or count_skip > 0:
                                condition_header = generate_main_status(CFG)
                                summary_msg = (
                                    f"️ <b>{condition_header}</b>\n"
                                    f"🌐 <b>Scanning:</b> [{display_zone}] {target_url}\n\n"
                                )

                                if added_in_zone:
                                    summary_msg += "\n".join(added_in_zone) + "\n\n"
                                else:
                                    summary_msg += "❌ ไม่มีไฟล์เข้าเงื่อนไข\n\n"             
                                    
                                footer = f"📊 <b>สรุป {display_zone}:</b> เพิ่มใหม่ {len(added_in_zone)} | ข้าม {count_skip}"
                                summary_msg += footer
                            
                                print(f"\n{footer}") # แสดงในหน้าจอ
                                send_notify(summary_msg) # ส่งแจ้งเตือนทีเดียว
                            # ======================================================

                        # บันทึกข้อมูลหลังจบ "ทุกโซน" 
                        save_data(SEEN_FILE, seen_ids)
                        save_data(HASH_SEEN_FILE, seen_hashes)
                
                # ปิด Browser เมื่อรันครบทุกโซนแล้วเท่านั้น
                browser.close()

            # จบรอบ เข้าสู่ช่วงพัก
            wait_sec = random.randint(SET.get('MIN_WAIT_MINUTES', 2)*60, SET.get('MAX_WAIT_MINUTES', 10)*60)
            wait_msg = f"💤 Cycle finished. Waiting {wait_sec//60} minutes for next scan..."
            
            # พิมพ์ลง Log แค่ครั้งเดียวว่ากำลังรอ
            print(wait_msg) 
            send_notify(wait_msg) 

            for s in range(wait_sec, 0, -1):
                # ใช้ \r เพื่อให้พิมพ์ทับบรรทัดเดิมใน Terminal 
                # และใช้ sys.stdout โดยตรงจะช่วยลดการเขียนลง Log ไฟล์ได้ในบางการตั้งค่า
                sys.stdout.write(f"\r⏳ Next cycle in: {s//60}m {s%60}s...   ")
                sys.stdout.flush()
                time.sleep(1)
            
            # เมื่อรอเสร็จค่อยพิมพ์ขึ้นบรรทัดใหม่
            print("\n🚀 Starting next cycle...")

        except Exception as e:
            print(f"❌ Global Error: {e}"); time.sleep(60)

if __name__ == "__main__":
    main()
