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

def handle_exit(sig, frame):
    # กำหนดเหตุผลตามสัญญาณที่ได้รับ
    reasons = {
        signal.SIGINT: "User Interrupted (Ctrl+C)",
        signal.SIGHUP: "Terminal Closed (SIGHUP)",
        signal.SIGTERM: "Process Killed (SIGTERM)"
    }
    reason = reasons.get(sig, f"Signal {sig}")
    stop_msg = f"🛑 BearBit Auto-Pilot : Stopped\nReason: {reason}"
    
    print(f"\n{stop_msg}")
    try:
        send_notify(stop_msg)
    except:
        pass
    sys.exit(0)

# ลงทะเบียนสัญญาณต่างๆ
signal.signal(signal.SIGINT, handle_exit)   # Ctrl+C
signal.signal(signal.SIGTERM, handle_exit)  # pkill / kill
if sys.platform != "win32":
    signal.signal(signal.SIGHUP, handle_exit)   # ปิดหน้าจอ Shell (เฉพาะ Linux/Mac)
    # บังคับ Encoding สำหรับ Windows
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer)

urllib3.disable_warnings()


# ========================= CONFIGURATION =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(BASE_DIR, "seen.txt")
HASH_SEEN_FILE = os.path.join(BASE_DIR, "hash_seen.txt")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

def load_full_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"❌ Error: ไม่พบไฟล์ {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def send_notify(msg):
    """ส่งแจ้งเตือนผ่าน LINE, Telegram และ Discord"""
    cfg = load_full_config()
    
    # 1. LINE Notify
    line_cfg = cfg.get('LINE_CONFIG', {})
    if line_cfg.get('enable'):
        token = line_cfg.get('access_token')
        if token:
            try: requests.post('https://notify-api.line.me/api/notify', headers={'Authorization': f'Bearer {token}'}, data={'message': msg.strip()}, timeout=10)
            except: pass

    # 2. Telegram Bot
    tele_cfg = cfg.get('TELEGRAM_CONFIG', {})
    if tele_cfg.get('notify_enable'):
        t_token = tele_cfg.get('main_bot_token')
        t_id = tele_cfg.get('chat_id')
        if t_token and t_id:
            try: requests.post(f"https://api.telegram.org/bot{t_token}/sendMessage", json={'chat_id': t_id, 'text': msg.strip(), 'parse_mode': 'HTML'}, timeout=10)
            except: pass

    # 3. Discord Webhook [เพิ่มใหม่]
    disc_cfg = cfg.get('DISCORD_CONFIG', {})
    if disc_cfg.get('enable'):
        webhook_url = disc_cfg.get('webhook_url')
        if webhook_url:
            try:
                # ดึง ID ของ Admin มาจาก Config (ถ้ามี)
                admin_id = disc_cfg.get('admin_id', '').strip()
                
                # ถ้ามี ID ให้เตรียมรูปแบบการ Mention <@ID>
                mention = f"<@{admin_id}> " if admin_id else ""
                
                # ตกแต่งข้อความ: เอา Mention วางไว้หน้าสุดเพื่อให้ระบบแจ้งเตือนถึงตัวบุคคล
                payload = {
                    "content": f"{mention}**[BearBit Notification]**\n{msg.strip()}"
                }
                
                requests.post(webhook_url, json=payload, timeout=10)
            except: 
                pass

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
        self.name = cfg["name"]
        self.url = cfg["url"].rstrip("/")
        self.user = cfg["qb_user"]
        self.pw = cfg["qb_pass"]
        self.quota_gb = cfg.get("quota_gb", 0)
        self.auth = HTTPBasicAuth(self.user, self.pw) if cfg.get("nginx") else None

        self.s = requests.Session()
        self.free_gb = 0
        self.used_gb = 0
        self.jobs = 0
        self.is_connected = False
        self.stat_msg = ""

    def login(self):
        try:
            r = self.s.post(
                f"{self.url}/api/v2/auth/login",
                data={"username": self.user, "password": self.pw},
                auth=self.auth,
                verify=False,
                timeout=10
            )
            self.is_connected = (r.status_code == 200 and ("Ok." in r.text or r.cookies.get('SID')))
            return self.is_connected
        except:
            return False

    def refresh_status(self):
        if not self.is_connected:
            return False
        try:
            # 1. ดึงข้อมูล Torrent ทั้งหมดจาก WebAPI
            torrents = self.s.get(
                f"{self.url}/api/v2/torrents/info",
                auth=self.auth,
                verify=False,
                timeout=10
            ).json()

            # 2. นับจำนวนทั้งหมด และคัดกรองเฉพาะตัวที่กำลังทำงาน (Active)
            total = len(torrents)
            # สถานะที่นับว่าเป็น Active: กำลังโหลด, กำลังส่ง, หรือกำลังตรวจสอบไฟล์
            active_states = ['downloading', 'uploading', 'stalledUP', 'stalledDL', 'starting', 'checkingUP', 'checkingDL']
            active = sum(1 for t in torrents if t.get('state') in active_states)

            self.jobs = total
            self.stat_msg = f"Active/Total: {active}/{total}"

            # 3. คำนวณพื้นที่ที่ใช้งานไป (USED) เพื่อใช้ร่วมกับระบบ Quota
            self.used_gb = sum(t.get('size', 0) for t in torrents) / (1024**3)

            # 4. คำนวณพื้นที่ว่าง (FREE)
            if self.quota_gb > 0:
                # กรณีตั้งโควต้าไว้: ใช้ Quota ลบด้วยขนาดไฟล์ทั้งหมดที่มีใน List
                self.free_gb = max(0, self.quota_gb - self.used_gb)
            else:
                # กรณีไม่ได้ตั้งโควต้า: ดึงค่าจาก Disk จริงของเซิร์ฟเวอร์
                r_main = self.s.get(
                    f"{self.url}/api/v2/sync/maindata",
                    auth=self.auth,
                    verify=False,
                    timeout=10
                ).json()
                disk_free = r_main.get('server_state', {}).get('free_space_on_disk', 0)
                self.free_gb = disk_free / (1024**3)

            return True
        except Exception as e:
            # เก็บ Error ไว้ดูใน console ถ้าเกิดปัญหา
            print(f"[{self.name}] Refresh Status Error: {e}")
            return False

    def add(self, content, size=None, n_cfg=None): # เพิ่ม parameter ให้รองรับ 3 ตัว
        try:
            r = self.s.post(
                f"{self.url}/api/v2/torrents/add",
                files={"torrents": ("f.torrent", content)},
                data={"paused": "false"},
                auth=self.auth,
                verify=False,
                timeout=30
            )
            return r.status_code == 200
        except:
            return False

    def delete_torrent(self, hash_str):
        try:
            self.s.post(
                f"{self.url}/api/v2/torrents/delete",
                data={"hashes": hash_str, "deleteFiles": "true"},
                auth=self.auth, verify=False, timeout=10
            )
            return True
        except: return False
            
class RtorrentNode:
    def __init__(self, cfg):
        self.name, self.url = cfg["name"], cfg["url"].rstrip("/")
        self.user, self.pw = cfg["rt_user"], cfg["rt_pass"]
        self.quota_gb = cfg.get("quota_gb", 0)
        self.auth = HTTPBasicAuth(self.user, self.pw)
        self.free_gb, self.is_connected = 0, False
        self.jobs = 0
        self.stat_msg = ""

    def login(self):
        try:
            r = requests.post(self.url, data='<?xml version="1.0"?><methodCall><methodName>system.listMethods</methodName></methodCall>', auth=self.auth, timeout=10, verify=False)
            self.is_connected = (r.status_code == 200); return self.is_connected
        except: return False

    def refresh_status(self):
        if not self.is_connected: return False
        try:
            xml = '<?xml version="1.0"?><methodCall><methodName>d.multicall2</methodName><params><param><value><string></string></value></param><param><value><string>main</string></value></param><param><value><string>d.is_active=</string></value></param><param><value><string>d.size_bytes=</string></value></param></params></methodCall>'
            soup = BeautifulSoup(requests.post(self.url, data=xml, auth=self.auth, timeout=10, verify=False).text, "xml")
            vals = [v.get_text() for v in soup.find_all("i8")]
            total, active, used_bytes = len(vals)//2, 0, 0
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

    def add(self, content, size=None, n_cfg=None): # ปรับให้เหมือนกัน
        try:
            b64 = base64.b64encode(content).decode('utf-8')
            xml = f'<?xml version="1.0"?><methodCall><methodName>load.raw_start</methodName><params><param><value><string></string></value></param><param><value><base64>{b64}</base64></value></param></params></methodCall>'
            return requests.post(self.url, data=xml, auth=self.auth, timeout=30, verify=False).status_code == 200
        except: return False

    def delete_torrent(self, hash_str):
        try:
            # rTorrent ใช้ d.erase เพื่อลบทั้งรายการและไฟล์
            xml = f'<?xml version="1.0"?><methodCall><methodName>d.erase</methodName><params><param><value><string>{hash_str}</string></value></param></params></methodCall>'
            requests.post(self.url, data=xml, auth=self.auth, timeout=10, verify=False)
            return True
        except: return False

# ========================= AUTO VOTE =========================

def auto_vote_snatched(page):
    try:
        max_p = 5
        print(f"🗳️ เริ่มระบบโหวตอัตโนมัติ (จำกัด {max_p} หน้า)")
        send_notify(f"🗳️ เริ่มระบบโหวตอัตโนมัติ (จำกัด {max_p} หน้า)")
        page.goto("https://bearbit.org/snatchdown.php", wait_until="networkidle")
        for p_idx in range(1, max_p + 1):
            vote_targets = page.locator('img[title="ยอดเยี่ยม"], img[src*="v5.1.1.png"]')
            count = vote_targets.count()
            if count > 0:
                for i in range(count):
                    try: vote_targets.first.click(); time.sleep(random.uniform(1.0, 2.0))
                    except: continue
                print(f"📄 หน้า {p_idx}: โหวตเรียบร้อย {count} รายการ")
            else:
                print(f"📄 หน้า {p_idx}: ไม่มีรายการให้โหวต")
            
            next_btn = page.locator('img[src*="nextpage.gif"]').first
            if next_btn.is_visible() and p_idx < max_p: 
                next_btn.click(); time.sleep(2)
            else: break
        print("🎊 จบการทำงานระบบโหวตประจำรอบ")
        send_notify("🎊 จบการทำงานระบบโหวตประจำรอบ")
    except Exception as e: print(f"❌ ระบบโหวตขัดข้อง: {e}")

# ========================= AUTO THANKS =========================

def click_thanks(page, torrent_id):
    """สั่งรัน JavaScript เพื่อกดขอบคุณตาม ID ของ Torrent"""
    try:
        # สั่งรันฟังก์ชัน sndReq ของทางเว็บโดยตรง
        page.evaluate(f"sndReq('action=say_thanks&id={torrent_id}', 'saythanks')")
        print(f"     🙏 ให้กำลังใจ: กด 'ขอบคุณ' เรียบร้อย (ID: {torrent_id})")
        send_notify(f"     🙏 ให้กำลังใจ: กด 'ขอบคุณ' เรียบร้อย (ID: {torrent_id})")
        return True
    except Exception as e:
        print(f"     ⚠️ ไม่สามารถกดขอบคุณได้: {e}")
        return False
        
# ========================= AUTO CLEAN =========================

class NodeCleaner:
    def __init__(self, node_obj, node_clean_cfg, global_clean_cfg):
        self.node = node_obj
        self.node_cfg = node_clean_cfg or {}
        self.global_cfg = global_clean_cfg or {}

    def process(self):
        # ตรวจสอบว่าระบบถูกเปิดใช้งานหรือไม่ (ลำดับ: Node > Global)
        is_enabled = self.node_cfg.get('enable')
        if is_enabled is None: # ถ้าใน Node ไม่ได้ตั้งค่าไว้ ให้ไปดูที่ Global
            is_enabled = self.global_cfg.get('enable', False)
        
        if not is_enabled: return
        
        print(f"🧹 [{self.node.name}] Checking for expired torrents...")
        
        try:
            if isinstance(self.node, QbitNode):
                self._clean_qbit()
            elif isinstance(self.node, RtorrentNode):
                self._clean_rtorrent()
        except Exception as e:
            print(f"⚠️ [{self.node.name}] Clean Error: {e}")

    def _clean_qbit(self):
        # ดึงข้อมูลจาก API ของ qBittorrent
        r = self.node.s.get(f"{self.node.url}/api/v2/torrents/info", 
                            auth=self.node.auth, verify=False, timeout=15)
        if r.status_code != 200: return
        
        torrents = r.json()
        now = time.time()
        for t in torrents:
            ratio = t.get('ratio', 0)
            added_on = t.get('added_on', 0)
            age_hours = (now - added_on) / 3600
            
            if self._should_remove(ratio, age_hours):
                if self.node.delete_torrent(t['hash']):
                    msg = f"   🗑️ Removed: {t['name'][:30]} (Ratio: {ratio:.2f}, Age: {age_hours:.1f}h)"
                    print(msg)

    def _clean_rtorrent(self):
        xml = '<?xml version="1.0"?><methodCall><methodName>d.multicall2</methodName><params><param><value><string></string></value></param><param><value><string>main</string></value></param><param><value><string>d.hash=</string></value></param><param><value><string>d.ratio=</string></value></param><param><value><string>d.timestamp.finished=</string></value></param><param><value><string>d.name=</string></value></param></params></methodCall>'
        r = requests.post(self.node.url, data=xml, auth=self.node.auth, verify=False, timeout=15)
        if r.status_code != 200: return
        
        soup = BeautifulSoup(r.text, "xml")
        data = [v.get_text() for v in soup.find_all("string")]
        now = time.time()
        
        for i in range(0, len(data), 4):
            t_hash, t_ratio_raw, t_time, t_name = data[i], data[i+1], data[i+2], data[i+3]
            ratio = int(t_ratio_raw) / 1000 
            # ป้องกันกรณีไฟล์ยังไม่เสร็จ (timestamp เป็น 0)
            t_finish = int(t_time)
            age_hours = (now - t_finish) / 3600 if t_finish > 0 else 0
            
            if age_hours > 0 and self._should_remove(ratio, age_hours):
                if self.node.delete_torrent(t_hash):
                    print(f"   🗑️ Removed: {t_name[:30]} (Ratio: {ratio:.2f}, Age: {age_hours:.1f}h)")

    def _should_remove(self, ratio, age_hours):
        # ลำดับความสำคัญของ Config: Node > Global > Default
        min_ratio = self.node_cfg.get('min_ratio') or self.global_cfg.get('min_ratio') or 0.5
        min_time = self.node_cfg.get('min_time') or self.global_cfg.get('min_time') or 360
        max_time = self.node_cfg.get('max_time') or self.global_cfg.get('max_time') or 720
        
        # 1. อยู่มานานจนเกิน Max Time (ลบทันที)
        if age_hours >= max_time: return True
        # 2. อยู่เกิน Min Time และ Ratio ถึงเป้า
        if age_hours >= min_time and ratio >= min_ratio: return True
        
        return False
        
# ========================= MAIN LOOP =========================

def main():
    startup_msg = "🚀 BearBit Auto-Pilot : Started"
    print(startup_msg)
    send_notify(startup_msg)
    
    while True:
        try:
            CFG = load_full_config(); SET = CFG.get('SETTING', {}); global_clean = CFG.get('GLOBAL_CLEAN', {})
            seen_ids, seen_hashes = load_data(SEEN_FILE), load_data(HASH_SEEN_FILE)
            active_nodes = []
            node_status_lines = []
            # 1. เชื่อมต่อโหนด
            print("\n🔌 QB/RTฺ NODE STATUS (START)\n")

            for n_cfg in CFG['NODES']:
                if not n_cfg.get('enable'): continue # ข้ามถ้า Node ถูกปิดใช้งาน

                node = RtorrentNode(n_cfg) if n_cfg.get("type") == "rtorrent" else QbitNode(n_cfg)

                try:
                    if node.login() and node.refresh_status():
                        active_nodes.append((node, n_cfg))
                        
                        # ระบบ Auto Clean
                        node_clean = n_cfg.get('clean_settings', {})
                        cleaner = NodeCleaner(node, node_clean, global_clean)
                        cleaner.process()
                        
                        line = f"[{node.name}] 🟢 FREE {node.free_gb:.2f}GB | {node.stat_msg}"
                    else:
                        line = f"[{node.name}] ❌ CONNECTION ERROR"
                except Exception as e:
                    line = f"[{node.name}] ⚠️ CRITICAL ERROR: {e}"
                    
                print(line)
                node_status_lines.append(line)

            print("\n🔌 QB/RT NODE STATUS (END)\n")

            # ✅ ส่งรวมทีเดียว (สำคัญมาก)
            send_notify(
                "🔌 QB NODE STATUS\n\n" +
                "\n".join(node_status_lines)
            )

            # 2. เริ่มสแกน Browser
            with sync_playwright() as p:
                browser, b_path = launch_any_browser(p)
                context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
                page = context.new_page()
                page.goto("https://bearbit.org/login.php")
                page.fill('input[name="username"]', CFG['BEARBIT']['username'])
                page.fill('input[name="password"]', CFG['BEARBIT']['password'])
                page.click('input[type="submit"]'); time.sleep(2)

                if "logout.php" in page.content():
                    print("🔑 Bearbit Login: Success")
                    send_notify("🔑 Bearbit Login: Success")
                    auto_vote_snatched(page)
                    
                    filter_info = f"⚙️ เงื่อนไข: ขนาด {SET.get('MIN_SIZE_GB', 0)}-{SET.get('MAX_SIZE_GB', 999)}GB | ฟรีโหลด {'เปิด' if SET.get('FREELOAD_ENABLE') else 'ปิด'} ({SET.get('MIN_FREE_PERCENT', 0)}%)"
                    print(filter_info)
                    send_notify(filter_info)

                    dl_session = requests.Session()
                    dl_session.cookies.update({c['name']: c['value'] for c in context.cookies()})

                    for target_url in CFG['BEARBIT']['target_urls']:
                        u_name = target_url.split('/')[-1]
                        print(f"🌐 Scanning: {target_url}")
                        send_notify(f"🌐 Scanning: {target_url}")
                        page.goto(target_url); soup = BeautifulSoup(page.content(), "html.parser")
                        added_count = 0; skipped_count = 0
                        
                        # ค้นหาแถวรายการ Torrent
                        rows = soup.find_all("tr")
                        for row in rows:
                            # ดึงลิงก์และชื่อไฟล์
                            link_tag = row.find("a", href=re.compile(r"details\.php\?id=\d+"))
                            dl_link_tag = row.find("a", href=re.compile(r"download(new)?\.php\?id=\d+"))
                            
                            if not dl_link_tag or not link_tag: continue
                            
                            t_name = link_tag.get_text().strip()
                            t_id = re.search(r'id=(\d+)', dl_link_tag['href']).group(1)
                            
                            # แสดง Log เริ่มต้นการตรวจสอบไฟล์
                            print(f"  🔍 Checking: {t_name[:60]}...")

                            # 1. ตรวจสอบว่าเคยเพิ่มไปหรือยัง
                            if t_id in seen_ids: 
                                print(f"     ❌ ข้าม: เคยเพิ่มไปแล้ว (ID: {t_id})")
                                skipped_count += 1; continue

                            # 2. ตรวจสอบขนาดไฟล์
                            t_size_gb = 0
                            for cell in row.find_all("td"):
                                if re.search(r"\d+\s*(GB|MB|TB)", cell.get_text(), re.I):
                                    t_size_gb = parse_size(cell.get_text()); break
                            
                            if not (SET.get('MIN_SIZE_GB', 0) <= t_size_gb <= SET.get('MAX_SIZE_GB', 999)):
                                print(f"     ❌ ข้าม: ขนาด {t_size_gb:.2f}GB ไม่ตรงเงื่อนไข")
                                skipped_count += 1; continue

                            # 3. ตรวจสอบสถานะ Freeload
                            free_p = check_freeload_status(row) if SET.get('FREELOAD_ENABLE') else 100
                            if free_p < SET.get('MIN_FREE_PERCENT', 0):
                                print(f"     ❌ ข้าม: ฟรีโหลด {free_p}% น้อยกว่าที่กำหนด")
                                skipped_count += 1; continue
                            
                            # 4. ตรวจสอบ Info Hash (ป้องกันไฟล์ซ้ำคนละ ID)
                            r_dl = dl_session.get(f"https://bearbit.org/{dl_link_tag['href'].lstrip('/')}")
                            if r_dl.status_code == 200:
                                t_hash = extract_info_hash(r_dl.content)
                                if t_hash and t_hash in seen_hashes: 
                                    print(f"     ❌ ข้าม: พบ Hash ซ้ำในระบบ (ไฟล์เดียวกัน)")
                                    seen_ids.add(t_id); skipped_count += 1; continue
                                
                                # [เพิ่มใหม่] กดขอบคุณก่อนส่งไฟล์เข้า Node
                                # เราใช้ page เดิมที่เปิด target_url อยู่ในการกด
                                click_thanks(page, t_id)
                                time.sleep(random.uniform(0.5, 1.2)) # รอจังหวะเล็กน้อยเหมือนคนกด
                                
                                # คัดเลือก Node ที่ว่างที่สุด
                                active_nodes.sort(key=lambda x: (x[0].free_gb - x[0].jobs), reverse=True)
                                target_node, target_cfg = active_nodes[0]
                                
                                if target_node.add(r_dl.content, t_size_gb, target_cfg):
                                    msg = f"📥 [Success] {target_node.name} | {t_size_gb:.1f}GB | {t_name[:40]}"
                                    send_notify(msg); print(f"     {msg}")
                                    seen_ids.add(t_id)
                                    if t_hash:
                                        seen_hashes.add(t_hash)
                                    added_count += 1
                            
                            if added_count >= SET.get('MAX_NEW_PER_ZONE', 5): 
                                print(f"  ⚠️ หยุดสแกนโซนนี้: ครบโควตา {added_count} ไฟล์แล้ว")
                                send_notify(f"  ⚠️ หยุดสแกนโซนนี้: ครบโควตา {added_count} ไฟล์แล้ว")
                                break
                        
                        summary_msg = f"📊 สรุป {u_name}: เพิ่มใหม่ {added_count} | ข้าม {skipped_count}"
                        print(summary_msg); send_notify(summary_msg)
                        save_data(SEEN_FILE, seen_ids); save_data(HASH_SEEN_FILE, seen_hashes)
                
                browser.close()

            wait_sec = random.randint(SET.get('MIN_WAIT_MINUTES', 2)*60, SET.get('MAX_WAIT_MINUTES', 10)*60)
            wait_msg = f"💤 Cycle finished. Waiting {wait_sec//60} minutes for next scan..."
            print(f"{wait_msg}")
            send_notify(wait_msg) 

            for s in range(wait_sec, 0, -1):
                sys.stdout.write(f"\r⏳ Next cycle in: {s//60}m {s%60}s...   ")
                sys.stdout.flush()
                time.sleep(1)
            print("")

        except Exception as e:
            print(f"❌ Error: {e}")
            send_notify(f"❌ Error in loop: {e}") # แจ้งเตือน error ภายใน loop ด้วย
            time.sleep(10)
            
if __name__ == "__main__":
    main()