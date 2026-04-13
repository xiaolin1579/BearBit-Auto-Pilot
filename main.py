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
from requests.auth import HTTPBasicAuth
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

def load_full_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"❌ Error: ไม่พบไฟล์ {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def send_notify(msg, raw_data=None):
    """
    ส่งแจ้งเตือนผ่าน Messaging API (Flex Message), Telegram (HTML) และ Discord (Markdown)
    :param msg: ข้อความต้นฉบับที่มีแท็ก <b> </b>
    :param raw_data: (Optional) dict ข้อมูลดิบสำหรับสร้าง Flex Message ที่สวยงาม
    """
    cfg = load_full_config()
    msg = msg.strip()
    
    # เตรียมข้อความสำหรับแต่ละแพลตฟอร์ม
    # Discord: เปลี่ยน <b> เป็น **
    discord_msg = msg.replace('<b>', '**').replace('</b>', '**')
    # LINE Text: ลบแท็กออก (กรณีส่งแบบ Text ปกติ)
    line_clean_msg = msg.replace('<b>', '').replace('</b>', '')

    # 1. LINE Messaging API (แทน LINE Notify)
    line_cfg = cfg.get('LINE_CONFIG', {})
    if line_cfg.get('enable') and line_cfg.get('access_token'):
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {line_cfg.get('access_token')}"
        }
        
        # ส่งแบบ Text (ถ้าต้องการความง่าย) หรือ Flex (ถ้าต้องการตัวหนา)
        # ในที่นี้ส่งแบบ Text ให้ก่อนเพื่อให้โค้ดไม่ซับซ้อน แต่เปลี่ยนเป็นตัวหนาในอนาคตได้
        payload = {
            "to": line_cfg.get('user_id'),
            "messages": [{"type": "text", "text": line_clean_msg}]
        }
        
        try: requests.post(url, json=payload, headers=headers, timeout=10)
        except: pass

    # 2. Telegram Bot (HTML)
    tele_cfg = cfg.get('TELEGRAM_CONFIG', {})
    if tele_cfg.get('notify_enable') and tele_cfg.get('main_bot_token'):
        try:
            requests.post(
                f"https://api.telegram.org/bot{tele_cfg.get('main_bot_token')}/sendMessage",
                json={'chat_id': tele_cfg.get('chat_id'), 'text': msg, 'parse_mode': 'HTML'},
                timeout=10
            )
        except: pass

    # 3. Discord Webhook (Markdown)
    disc_cfg = cfg.get('DISCORD_CONFIG', {})
    if disc_cfg.get('enable') and disc_cfg.get('webhook_url'):
        try:
            admin_id = disc_cfg.get('admin_id', '').strip()
            mention = f"<@{admin_id}> " if admin_id else ""
            payload = {"content": f"{mention}**[BearBit Notification]**\n{discord_msg}"}
            requests.post(disc_cfg.get('webhook_url'), json=payload, timeout=10)
        except: pass

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

def check_freeload_status(soup_element):
    free_tag = soup_element.find("font", color="green")
    if not free_tag: return 0
    try: return int(re.sub(r'\D', '', free_tag.get_text()))
    except: return 0

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
            torrents = self.s.get(f"{self.url}/api/v2/torrents/info", auth=self.auth, verify=False, timeout=10).json()
            total = len(torrents)
            active_states = ['downloading', 'uploading', 'stalledUP', 'stalledDL', 'starting', 'checkingUP', 'checkingDL']
            active = sum(1 for t in torrents if t.get('state') in active_states)
            self.jobs = total
            self.stat_msg = f"Active/Total: {active}/{total}"
            used_gb = sum(t.get('size', 0) for t in torrents) / (1024**3)
            if self.quota_gb > 0: self.free_gb = max(0, self.quota_gb - used_gb)
            else:
                r_main = self.s.get(f"{self.url}/api/v2/sync/maindata", auth=self.auth, verify=False, timeout=10).json()
                self.free_gb = r_main.get('server_state', {}).get('free_space_on_disk', 0) / (1024**3)
            return True
        except: return False

    def add(self, content, size=None, n_cfg=None):
        try:
            r = self.s.post(f"{self.url}/api/v2/torrents/add", files={"torrents": ("f.torrent", content)}, data={"paused": "false"}, auth=self.auth, verify=False, timeout=30)
            return r.status_code == 200
        except: return False

    def delete_torrent(self, hash_str):
        try:
            self.s.post(f"{self.url}/api/v2/torrents/delete", data={"hashes": hash_str, "deleteFiles": "true"}, auth=self.auth, verify=False, timeout=10)
            return True
        except: return False

    def reannounce_all(self):
        """ สั่ง Re-announce ทุก Torrent ใน qBittorrent """
        if not self.is_connected and not self.login(): return False
        try:
            # สั่ง reannounce ทุก hashes โดยส่งค่า 'all'
            r = self.s.post(f"{self.url}/api/v2/torrents/reannounce", data={"hashes": "all"}, auth=self.auth, timeout=10)
            return r.status_code == 200
        except: return False

class RtorrentNode:
    def __init__(self, cfg):
        self.name, self.url = cfg["name"], cfg["url"].rstrip("/")
        self.user, self.pw = cfg["rt_user"], cfg["rt_pass"]
        self.quota_gb = cfg.get("quota_gb", 0)
        self.auth = HTTPBasicAuth(self.user, self.pw)
        self.free_gb, self.is_connected = 0, False
        self.jobs = 0
        self.stat_msg = "Active/Total: 0/0"

    def login(self):
        try:
            r = requests.post(self.url, data='<?xml version="1.0"?><methodCall><methodName>system.listMethods</methodName></methodCall>', auth=self.auth, timeout=10, verify=False)
            self.is_connected = (r.status_code == 200)
            return self.is_connected
        except: return False

    def refresh_status(self):
        if not self.is_connected: return False
        try:
            xml = '<?xml version="1.0"?><methodCall><methodName>d.multicall2</methodName><params><param><value><string></string></value></param><param><value><string>main</string></value></param><param><value><string>d.is_active=</string></value></param><param><value><string>d.size_bytes=</string></value></param></params></methodCall>'
            soup = BeautifulSoup(requests.post(self.url, data=xml, auth=self.auth, timeout=10, verify=False).text, "xml")
            vals = [v.get_text() for v in soup.find_all("i8")]
            total, active, used_bytes = len(vals)//2, 0, 0
            self.jobs = total
            for i in range(0, len(vals), 2):
                if int(vals[i]) == 1: active += 1
                used_bytes += int(vals[i+1])
            self.stat_msg = f"Active/Total: {active}/{total}"
            used_gb = used_bytes / (1024**3)
            if self.quota_gb > 0: self.free_gb = max(0, self.quota_gb - used_gb)
            else:
                r_free = requests.post(self.url, data='<?xml version="1.0"?><methodCall><methodName>network.disk_free</methodName></methodCall>', auth=self.auth, timeout=10, verify=False)
                self.free_gb = abs(int(BeautifulSoup(r_free.text, "xml").find("value").get_text().strip())) / (1024**3)
            return True
        except: return False

    def add(self, content, size=None, n_cfg=None):
        try:
            b64 = base64.b64encode(content).decode('utf-8')
            xml = f'<?xml version="1.0"?><methodCall><methodName>load.raw_start</methodName><params><param><value><string></string></value></param><param><value><base64>{b64}</base64></value></param></params></methodCall>'
            return requests.post(self.url, data=xml, auth=self.auth, timeout=30, verify=False).status_code == 200
        except: return False

    def delete_torrent(self, t_hash):
        try:
            xml = f'<?xml version="1.0"?><methodCall><methodName>d.erase</methodName><params><param><value><string>{t_hash}</string></value></param></params></methodCall>'
            return requests.post(self.url, data=xml, auth=self.auth, verify=False, timeout=10).status_code == 200
        except: return False

    def reannounce_all(self):
        """ สั่ง Re-announce ทุก Torrent ใน rTorrent โดยวนลูปส่ง XML-RPC """
        if not self.is_connected and not self.login(): return False
        try:
            # ดึงรายชื่อ hashes ทั้งหมดก่อน
            xml_list = '<?xml version="1.0"?><methodCall><methodName>download_list</methodName></methodCall>'
            r_list = requests.post(self.url, data=xml_list, auth=self.auth, timeout=10, verify=False)
            soup = BeautifulSoup(r_list.text, "xml")
            hashes = [s.get_text() for s in soup.find_all("string")]
            
            # วนลูปสั่ง announce ทีละตัว (rTorrent มาตรฐาน)
            for h in hashes:
                xml_ann = f'<?xml version="1.0"?><methodCall><methodName>d.tracker_announce</methodName><params><param><value><string>{h}</string></value></param></params></methodCall>'
                requests.post(self.url, data=xml_ann, auth=self.auth, timeout=5, verify=False)
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

    def process(self):
        node_enable = self.node_cfg.get('enable')
        global_enable = self.global_cfg.get('enable', False)

        if node_enable is True:
            is_enabled = True
        elif node_enable is False:
            is_enabled = global_enable   # 🔥 fallback ไป global
        else:
            is_enabled = global_enable   
            
        if not is_enabled: return

        print(f"🧹 [{self.node.name}] Checking for expired torrents...")
        try:
            removed_list = []
            if isinstance(self.node, QbitNode): removed_list = self._clean_qbit()
            elif isinstance(self.node, RtorrentNode): removed_list = self._clean_rtorrent()
            
            if removed_list:
                msg = f"🧹 [{self.node.name}] Cleanup Summary:\n" + "\n".join(removed_list)
                send_notify(msg)
        except Exception as e:
            print(f"⚠️ [{self.node.name}] Clean Error: {e}")

    def _clean_qbit(self):
        res = []
        r = self.node.s.get(f"{self.node.url}/api/v2/torrents/info", auth=self.node.auth, verify=False, timeout=15)
        if r.status_code != 200: return []
        torrents = r.json()
        now = time.time()
        for t in torrents:
            # 1. ข้ามถ้ายังโหลดไม่เสร็จ (progress น้อยกว่า 100%)
            if t.get('progress', 0) < 1: 
                continue
        
            # 2. ข้ามถ้าค่าเวลาโหลดเสร็จผิดปกติ
            completion_on = t.get('completion_on', 0)
            if completion_on <= 0:
                continue

            # 3. คำนวณเวลา Seeding จริง
            age_hours = (now - completion_on) / 3600
            ratio = t.get('ratio', 0)
            if self._should_remove(ratio, age_hours):
                if self.node.delete_torrent(t['hash']):
                    line = f"   🗑️ Removed: {t['name'][:30]} (Ratio: {ratio:.2f}, Seeding: {age_hours:.1f}h)"
                    print(line); res.append(line)
        return res

    def _clean_rtorrent(self):
        res = []
        # XML query สำหรับดึงข้อมูลที่จำเป็น
        xml = '<?xml version="1.0"?><methodCall><methodName>d.multicall2</methodName><params><param><value><string></string></value></param><param><value><string>main</string></value></param><param><value><string>d.hash=</string></value></param><param><value><string>d.ratio=</string></value></param><param><value><string>d.timestamp.finished=</string></value></param><param><value><string>d.name=</string></value></param></params></methodCall>'
        
        try:
            r = requests.post(self.node.url, data=xml, auth=self.node.auth, verify=False, timeout=15)
            if r.status_code != 200:
                print(f"⚠️ [{self.node.name}] Connection Error: HTTP {r.status_code}")
                return []

            soup = BeautifulSoup(r.text, "xml")
            # ความเสถียรสูง: เจาะจงไปที่ methodResponse ตามมาตรฐาน XML-RPC
            response = soup.find('methodResponse')
            if not response:
                return []
                
            torrent_entries = response.find_all('data')
            now = time.time()

            for entry in torrent_entries:
                # ดึงค่าเฉพาะชั้นนอกสุดเพื่อป้องกันข้อมูลปนกัน
                vals = [v.get_text().strip() for v in entry.find_all('value', recursive=False)]
                
                # ตรวจสอบความครบถ้วนของข้อมูล (Hash, Ratio, Finished, Name)
                if len(vals) < 4:
                    continue
                
                t_hash = vals[0]
                # แปลง Ratio: rTorrent ส่งมาเป็น 1/1000 (เช่น 1500 คือ 1.5)
                ratio = int(vals[1]) / 1000 if vals[1].isdigit() else 0
                t_finish = int(vals[2]) if vals[2].isdigit() else 0
                t_name = vals[3]

                # กรองเฉพาะไฟล์ที่โหลดเสร็จแล้วเท่านั้น
                if t_finish <= 0:
                    continue

                age_hours = (now - t_finish) / 3600

                # ตรวจสอบเงื่อนไขการลบตาม Config
                if self._should_remove(ratio, age_hours):
                    if self.node.delete_torrent(t_hash):
                        # ความสวยงาม: รายละเอียดชัดเจนแต่กระชับ
                        line = f"  - 🗑️ {t_name[:35]}... (R:{ratio:.2f}, Seeding:{age_hours:.1f}h)"
                        print(line)
                        res.append(line)

        except Exception as e:
            # Error Handling: พิมพ์สาเหตุออกมาให้ทราบ
            print(f"⚠️ [{self.node.name}] rTorrent Clean Error: {str(e)}")
            
        return res

    def _should_remove(self, ratio, age_hours):
        #ตรวจสอบว่า Node มีการตั้งค่าเฉพาะตัวและเปิดใช้งานอยู่หรือไม่
        use_node_cfg = self.node_cfg.get('enable', False)
        
        if use_node_cfg:
            # ถ้า Node เปิดอยู่: ใช้ค่าจาก Node (ถ้าไม่มีค่าใน Node ให้ใช้ Default)
            min_ratio = self.node_cfg.get('min_ratio', 0.5)
            min_time_m = self.node_cfg.get('min_time', 360)
            max_time_m = self.node_cfg.get('max_time', 1440)
        else:
            # ถ้า Node ปิดอยู่: บังคับไปใช้ Global (ถ้าไม่มี Global ให้ใช้ Default)
            min_ratio = self.global_cfg.get('min_ratio', 0.5)
            min_time_m = self.global_cfg.get('min_time', 360)
            max_time_m = self.global_cfg.get('max_time', 1440)        

        # แปลงนาทีเป็นชั่วโมง
        min_time = min_time_m / 60
        max_time = max_time_m / 60
        
        # 1. อยู่มานานจนเกิน Max Time (ลบทันที)
        if age_hours >= max_time: 
            return True
            
        # 2. อยู่เกิน Min Time และ Ratio ถึงเป้า
        if age_hours >= min_time and ratio >= min_ratio: 
            return True
        
        return False

# ========================= BEARBIT STATUS =========================

def get_stats_diff(current_data):
    """เปรียบเทียบค่าปัจจุบันกับค่าที่บันทึกไว้ (รองรับการแปลงหน่วย TB/GB/MB)"""
    diff_msg = ""
    if os.path.exists(STATS_CACHE_FILE):
        with open(STATS_CACHE_FILE, 'r', encoding='utf-8') as f:
            old_data = json.load(f)
        
        # 1. เทียบ Ratio และ Bonus (ใช้เลขตรงๆ)
        def calc_num_diff(curr, old, precision=3):
            c = float(str(curr).replace(',', ''))
            o = float(str(old).replace(',', ''))
            res = c - o
            if res == 0: return "0"
            return f"+{res:.{precision}f}" if res > 0 else f"{res:.{precision}f}"

        # 2. เทียบ Upload/Download (ต้องแปลงหน่วยก่อนลบ)
        def calc_size_diff(curr_str, old_str):
            curr_gb = parse_size(curr_str) # ใช้ฟังก์ชัน parse_size ที่คุณมีในโปรแกรม
            old_gb = parse_size(old_str)
            diff_gb = curr_gb - old_gb
            
            if diff_gb == 0: return "0"
            if abs(diff_gb) >= 1024:
                return f"+{diff_gb/1024:.2f} TB" if diff_gb > 0 else f"{diff_gb/1024:.2f} TB"
            return f"+{diff_gb:.2f} GB" if diff_gb > 0 else f"{diff_gb:.2f} GB"

        r_diff = calc_num_diff(current_data['ratio'], old_data['ratio'])
        up_diff = calc_size_diff(current_data['up'], old_data['up'])
        dl_diff = calc_size_diff(current_data['dl'], old_data['dl'])
        b_diff = calc_num_diff(current_data['bonus'], old_data['bonus'], 1)

        # สร้างข้อความส่วนต่าง (แสดงเฉพาะที่มีการเปลี่ยนแปลง)
        changes = []
        if r_diff != "0": changes.append(f"Ratio: ({r_diff})")
        if up_diff != "0": changes.append(f"Uploaded: ({up_diff})")
        if dl_diff != "0": changes.append(f"Downloaded: ({dl_diff})")
        if b_diff != "0": changes.append(f"Bonus: ({b_diff})")
        
        if changes:
            diff_msg = "\n📊 <b>Changes:</b> " + " | ".join(changes)

    # บันทึกค่าปัจจุบัน
    with open(STATS_CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(current_data, f)
    
    return diff_msg
    
def get_bearbit_stats(page):
    try:
        content = page.content()
        soup = BeautifulSoup(content, 'html.parser')
        user_tag = soup.find("a", href=re.compile(r"userdetails\.php\?id=\d+"))
        username = user_tag.get_text(strip=True) if user_tag else "Unknown"
        text = soup.get_text(separator=" ")

        # ดึงค่าดิบ
        ratio = re.search(r"Ratio:\s*([\d\.,]+)", text)
        up = re.search(r"Uploaded:\s*([\d\.,]+\s*[KMGTP]B)", text)
        dl = re.search(r"Downloaded:\s*([\d\.,]+\s*[KMGTP]B)", text)
        bonus = re.search(r"Bonus:\s*([\d\.,]+)", text)

        if ratio and up and dl:
            curr_data = {
                'ratio': ratio.group(1),
                'up': up.group(1),
                'dl': dl.group(1),
                'bonus': bonus.group(1) if bonus else "0",
            }
            
            diff_text = get_stats_diff(curr_data)
            
            # จัดรูปแบบบรรทัดเดียว (Inline Style)
            stats_msg = (
                f"👤 <b>{username}</b> | Ratio: {ratio.group(1)} | Uploaded: {up.group(1)} | Downloaded: {dl.group(1)} | "
                f"💰 Bonus: {curr_data['bonus']} "
                f"{' |' + diff_text.replace('📊 <b>Changes:</b>', '🔄') if diff_text else ''}"
            )
            return stats_msg

        return "⚠️ ไม่สามารถดึงสถิติได้"

    except Exception as e:
        return f"⚠️ Stats Error: {str(e)}"
        
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

def main():
    startup_msg = "🚀 BearBit Auto-Pilot : Started"
    print(startup_msg); send_notify(startup_msg)
    
    while True:
        try:
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
                    # 1.1 จัดการลบไฟล์เก่า (Cleanup)
                    NodeCleaner(node, n_cfg.get('clean_settings', {}), global_clean).process()
                    time.sleep(2)
                    # 1.2 สั่ง Re-announce Tracker (เพื่อให้ข้อมูล Upload/Download เป็นปัจจุบันที่สุด)
                    node.reannounce_all()
                    # 1.3 อัปเดตสถานะ Node (พื้นที่ว่าง/จำนวนงาน)
                    node.refresh_status()
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
                            print(f"⚙️ เงื่อนไข: ขนาด {SET.get('MIN_SIZE_GB', 0)}-{SET.get('MAX_SIZE_GB', 999)}GB | ฟรีโหลด {'เปิด' if SET.get('FREELOAD_ENABLE') else 'ปิด'}")
                        
                            if not safe_goto(target_url): continue
                            
                            soup = BeautifulSoup(page.content(), "html.parser")
                            added_in_zone = [] # เก็บ msg รายการที่เพิ่มสำเร็จ
                            count_skip = 0    # นับจำนวนที่ข้าม
                        
                            # ดึงรายการ Torrent
                            all_details = soup.find_all("a", href=re.compile(r"details(new)?\.php\?id=\d+"))
                            rows = list(dict.fromkeys([a.find_parent("tr") for a in all_details if not a.find("img") and len(a.get_text(strip=True)) > 5]))
                            
                            # --- วนลูปรายไฟล์ในโซน ---
                            for row in rows:
                                if not row or not ("download" in str(row).lower() or "free" in str(row).lower()): continue
                                link_tag = row.find("a", href=re.compile(r"details\.php\?id=\d+"))
                                dl_link_tag = row.find("a", href=re.compile(r"download(new)?\.php\?id=\d+"))
                                if not dl_link_tag or not link_tag: continue
                            
                                t_id = re.search(r'id=(\d+)', dl_link_tag.get('href', '')).group(1)
                                t_name = re.sub(r'(Auto Sticky:|Sticky:|HOT Torrents|\[FREE\]|\[HOT\]|\n|\t)', '', link_tag.get_text()).strip()
                                t_size_gb = parse_size(row.get_text(separator=" "))

                                print(f"  🔍 Checking: {t_name[:50]}... (ID: {t_id})")

                                # เช็คเงื่อนไขต่างๆ (Seen, Size, Free)
                                if t_id in seen_ids:
                                    print(f"      ❌ ข้าม: เคยเพิ่มไปแล้ว"); count_skip += 1; continue
                            
                                if not (SET.get('MIN_SIZE_GB', 0) <= t_size_gb <= SET.get('MAX_SIZE_GB', 999)):
                                    print(f"      ❌ ข้าม: ขนาด {t_size_gb:.2f}GB ไม่ตรงเงื่อนไข"); count_skip += 1; continue
                            
                                free_p = 100 if any(x in str(row) for x in ["pic/s-free.gif", "pic/s-x2.gif", "x2", "x6", "Free"]) else check_freeload_status(row)
                                if SET.get('FREELOAD_ENABLE') and free_p < SET.get('MIN_FREE_PERCENT', 0):
                                    print(f"      ❌ ข้าม: ฟรีโหลด {free_p}% ต่ำกว่ากำหนด"); count_skip += 1; continue

                                # ดาวน์โหลดและเพิ่มเข้า Node
                                r_dl = dl_session.get(f"https://bearbit.org/{dl_link_tag['href'].lstrip('/')}")
                                if r_dl.status_code == 200:
                                    t_hash = extract_info_hash(r_dl.content)
                                    if t_hash and t_hash in seen_hashes:
                                        print(f"      ❌ ข้าม: Hash ซ้ำในระบบ"); seen_ids.add(t_id); count_skip += 1; continue
                                
                                    # กดขอบคุณ
                                    page.evaluate(f"sndReq('action=say_thanks&id={t_id}', 'saythanks')")
                                
                                    # เลือก Node ที่ว่างที่สุด
                                    active_nodes.sort(key=lambda x: (x[0].free_gb - x[0].jobs), reverse=True)
                                    if active_nodes:
                                        node_obj, _ = active_nodes[0]
                                        if node_obj.add(r_dl.content):
                                            success_msg = f"📥 [Success] {node_obj.name} | {t_size_gb:.1f}GB | {t_name[:40]}"
                                            print(success_msg)
                                            added_in_zone.append(success_msg)
                                            seen_ids.add(t_id)
                                            if t_hash: seen_hashes.add(t_hash)

                                # เช็คโควตาต่อโซน
                                if len(added_in_zone) >= SET.get('MAX_NEW_PER_ZONE', 5): 
                                    print(f"  ⚠️ ครบโควตา {len(added_in_zone)} ไฟล์แล้ว")
                                    break

                            # ======================================================
                            # 📊 สรุปหลังจบแต่ละโซน (อยู่นอก Row loop แต่อยู่ใน Zone loop)
                            # ======================================================
                            if len(added_in_zone) > 0 or count_skip > 0:
                                summary_msg = (
                                    f"⚙️ <b>เงื่อนไข:</b> ขนาด {SET.get('MIN_SIZE_GB', 0):.1f}-{SET.get('MAX_SIZE_GB', 999):.1f}GB | ฟรีโหลด {'เปิด' if SET.get('FREELOAD_ENABLE') else 'ปิด'}\n"
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