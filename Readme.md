
# 🚀 BearBit Auto-Pilot (v2.0 Update)

**BearBit Auto-Pilot** คือระบบ Automation อัจฉริยะที่ช่วยบริหารจัดการการดาวน์โหลด Torrent จากเว็บไซต์ BearBit โดยเน้นความสะดวกสบาย ความรวดเร็ว และการรักษาค่า Ratio ของคุณอย่างมีประสิทธิภาพ พัฒนาด้วย Python และ Playwright พร้อมระบบบริหารจัดการพื้นที่จัดเก็บข้อมูลอัตโนมัติ

---

## ✨ คุณสมบัติเด่น (Key Features)

* **🔍 Smart Auto-Downloader:** ค้นหาและคัดเลือก Torrent ตามหมวดหมู่ (Target URLs) ที่คุณต้องการอัตโนมัติ
* **⚙️ Advanced Filtering:** กรองไฟล์ตามขนาด (Min/Max Size) และสถานะ **Freeload** (รองรับการเช็ค % ฟรีโหลดที่กำหนดเอง)
* **🤖 Multi-Node Distribution:** รองรับการเชื่อมต่อทั้ง **qBittorrent** และ **rTorrent** (XML-RPC) โดยระบบมีอัลกอริทึมเลือก Node ที่ "ว่างที่สุด" (Balance Load) อ้างอิงจากพื้นที่คงเหลือและจำนวนงาน
* **🧹 Intelligent Auto-Clean:** ระบบลบไฟล์ออกจาก Seedbox อัตโนมัติเมื่อถึงเป้าหมาย (Ratio ตามกำหนด หรือระยะเวลา Seed ขั้นต่ำ/สูงสุด) รองรับการตั้งค่าแยกราย Node หรือใช้ค่าส่วนกลาง (Global Clean)
* **🗳️ Auto-Gratitude & Vote:** * ระบบกด **"ขอบคุณ" (Thanks)** ก่อนดาวน์โหลด
    * ระบบ **"โหวตคะแนนยอดเยี่ยม"** ให้กับไฟล์ที่เคยโหลดไปแล้ว (Snatched) โดยอัตโนมัติ เพื่อช่วยสนับสนุนผู้อัปโหลดและรักษาสถานะบัญชี
* **📊 Zone-Based Summary:** ระบบรายงานผลการสแกนแบบแยกโซน แจ้งชัดเจนว่าในแต่ละ URL มีไฟล์ใหม่กี่ไฟล์ หรือไฟล์ไหนที่ไม่เข้าเงื่อนไข (❌ ไม่มีไฟล์เข้าเงื่อนไข)
* **🔔 Universal Notifications:** แจ้งเตือนสถานะการทำงานผ่าน 3 ช่องทางหลัก (Telegram, LINE Notify, Discord Webhook) พร้อมระบบ Mention เจาะจงตัวบุคคล
* **🛡️ Enhanced Stability:** ระบบ **Safe-Goto** พร้อมการลองใหม่ (Retry) อัตโนมัติหากหน้าเว็บโหลดช้า และใช้โหมด **Network Idle** เพื่อความแม่นยำในการอ่านข้อมูลหน้าเว็บ

---

## 🛠 การติดตั้งและเริ่มต้นใช้งาน (Getting Started)

### 1. เตรียมความพร้อม (Prerequisites)
เครื่องของคุณต้องติดตั้ง **Python 3.8+** และเบราว์เซอร์สำหรับ Playwright:

```bash
# ติดตั้ง Library ที่จำเป็น
pip install -r requirements.txt

# ติดตั้ง Browser Engine สำหรับ Playwright
playwright install chromium
```

### 2. การตั้งค่า (Configuration)
คัดลอกไฟล์ตัวอย่างและแก้ไขข้อมูลใน `config.json` โดยเน้นส่วนใหม่คือ `GLOBAL_CLEAN` และ `clean_settings` ในแต่ละ Node:

```bash
cp config.json.example config.json
```

### 3. เริ่มรันโปรแกรม (Execution)
```bash
# เริ่มระบบสแกนและจัดการไฟล์อัตโนมัติ
python main.py

# เริ่มระบบควบคุมระยะไกลผ่าน Telegram (ถ้าต้องการ)
python remote_control.py
```

---

## 📂 โครงสร้างไฟล์ที่สำคัญ

* `main.py`: สคริปต์หลัก (Core Engine) จัดการสแกน, ดาวน์โหลด, โหวต และลบไฟล์หมดอายุ
* `remote_control.py`: สคริปต์สำหรับสั่งการบอทผ่าน Telegram (Start/Stop/Status)
* `config.json`: ไฟล์ตั้งค่าหลัก (รหัสผ่าน, Tokens, เงื่อนไขการกรอง และการลบไฟล์)
* `seen.txt` / `hash_seen.txt`: ฐานข้อมูลประวัติเพื่อป้องกันการโหลดไฟล์ซ้ำและตรวจสอบ Hash ซ้ำซ้อน
* `script_run.log`: ไฟล์เก็บประวัติการทำงานและข้อผิดพลาด (Error Logs)

---

## 🛠 สคริปต์ช่วยเหลือ (Helper Scripts)

* **`manage_config` (bat/sh):** เมนูสำหรับตั้งค่าบัญชี, ตัวกรอง และจัดการ Node โดยไม่ต้องเปิดไฟล์ JSON เอง
* **`run_autopilot` (bat/sh):** ระบบรันอัตโนมัติที่จะเช็ค Library และ Browser ให้พร้อมก่อนเริ่มงานเสมอ

---

## ⚠️ ข้อควรระวัง (Disclaimer)
โปรแกรมนี้สร้างขึ้นเพื่ออำนวยความสะดวกในการบริหารจัดการข้อมูล ผู้ใช้งานควรตั้งค่า `MIN_WAIT_MINUTES` (ระยะเวลาพักรอบ) ให้เหมาะสม (แนะนำ 5-10 นาทีขึ้นไป) เพื่อไม่ให้เป็นการส่งคำขอไปยังเซิร์ฟเวอร์บ่อยจนเกินไป

---

**Developed with ❤️ for the BearBit Community.**
