
# 🚀 BearBit Auto-Pilot

**BearBit Auto-Pilot** คือระบบ Automation อัจฉริยะที่ช่วยบริหารจัดการการดาวน์โหลด Torrent จากเว็บไซต์ BearBit โดยเน้นความสะดวกสบาย ความรวดเร็ว และการรักษาค่า Ratio ของคุณอย่างมีประสิทธิภาพ พัฒนาด้วย Python และ Playwright

---

## ✨ คุณสมบัติเด่น (Key Features)

* **🔍 Smart Auto-Downloader:** ค้นหาและคัดเลือก Torrent ตามหมวดหมู่ที่คุณต้องการอัตโนมัติ
* **⚙️ Advanced Filtering:** กรองไฟล์ตามขนาด (Min/Max Size) และสถานะ **Freeload** (เลือกโหลดเฉพาะไฟล์ฟรี 100% หรือตามสัดส่วนที่กำหนด)
* **🤖 Multi-Node Distribution:** รองรับการเชื่อมต่อกับ Client หลายตัวพร้อมกัน ทั้ง **qBittorrent** และ **rTorrent** (XML-RPC) โดยระบบจะเลือกส่งไฟล์ไปยัง Node ที่มีพื้นที่ว่างมากที่สุด
* **🙏 Auto-Gratitude:** ระบบกด **"ขอบคุณ" (Thanks)** และ **"โหวต" (Vote)** ให้กับผู้อัปโหลดโดยอัตโนมัติก่อนเริ่มดาวน์โหลด
* **🔔 Universal Notifications:** แจ้งเตือนสถานะการทำงานผ่าน 3 ช่องทางหลัก:
    * **Telegram:** แจ้งเตือนสถานะและรองรับการสั่งงานระยะไกล (Remote Control)
    * **LINE Notify:** ส่งข้อความแจ้งเตือนเข้ากลุ่มหรือส่วนตัว
    * **Discord Webhook:** แจ้งเตือนพร้อมระบบ **Mention (<@ID>)** เจาะจงตัวบุคคล
* **🛡️ Signal Handling:** ระบบดักจับการปิดโปรแกรม (Ctrl+C หรือปิดหน้าจอ Shell) เพื่อส่งข้อความแจ้งเตือนสถานะสุดท้ายก่อนหยุดทำงาน
* **🔄 Remote Management:** ควบคุมบอทผ่าน Telegram (Start/Stop/Status) โดยไม่ต้องเข้าหน้าจอ Console

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
คัดลอกไฟล์ตัวอย่างและแก้ไขข้อมูลเป็นของคุณเอง:

```bash
cp config.json.example config.json
```
> **คำเตือน:** ห้ามอัปโหลดไฟล์ `config.json` ขึ้น GitHub หรือที่สาธารณะเนื่องจากมีรหัสผ่านและ Token ของคุณ

### 3. เริ่มรันโปรแกรม (Execution)
รันสคริปต์หลักเพื่อเริ่มระบบ Auto-Pilot:

```bash
python main.py
```

หากต้องการใช้ระบบควบคุมระยะไกลผ่าน Telegram:
```bash
python remote_control.py
```

---

## 🛠 เครื่องมือช่วยเหลือ (Helper Scripts)

โปรเจกต์นี้มาพร้อมกับสคริปต์ที่จะช่วยให้คุณจัดการระบบได้ง่ายขึ้นผ่าน Command Line โดยไม่ต้องแก้ไขไฟล์ JSON ด้วยตนเอง

### **1. ระบบจัดการการตั้งค่า (Config Manager)**
สคริปต์สำหรับตั้งค่าบัญชี, ระบบแจ้งเตือน, ตัวกรองไฟล์ และจัดการ Node (Client)
*  **Windows**: รันไฟล์ `manage_config.bat` 
*  **Linux/Unix**: รันคำสั่ง `bash manage_config.sh` 

**ฟีเจอร์ของ Config Manager:**
*  **Setup Account**: ตั้งค่า Username และ Password สำหรับเข้าใช้งาน BearBit 
*  **Notification**: ตั้งค่าการแจ้งเตือนและ Token สำหรับ Telegram, LINE Notify และ Discord Webhook 
*  **Filter Settings**: กำหนดขนาดไฟล์ขั้นต่ำ/สูงสุด และเงื่อนไขการโหลดไฟล์ฟรี (Freeload) 
*  **Global Auto-Clean**: ตั้งค่าระบบล้างข้อมูลในภาพรวม เช่น อัตรา Ratio ขั้นต่ำ หรือเวลาในการ Seed ไฟล์ 
*  **Node Management**: เพิ่ม, แก้ไข หรือลบข้อมูล Client (qBittorrent/rTorrent) พร้อมกำหนด Quota พื้นที่ใช้งาน 

### **2. ระบบรันโปรแกรมอัตโนมัติ (Auto-Run Scripts)**
 สคริปต์สำหรับตรวจสอบสภาพแวดล้อม ติดตั้ง Library และเริ่มทำงานทันที
*  **Windows**: รันไฟล์ `run_autopilot.bat` (รองรับการรันผ่าน Wine บนระบบ Linux) 
*  **Linux**: รันคำสั่ง `bash run_autopilot.sh` 

### **3. ระบบรันโปรแกรมบอทควบคุมอัตโนมัติ **
 สคริปต์สำหรับตรวจสอบสภาพแวดล้อม ติดตั้ง Library และเริ่มทำงานทันที
*  **Windows**: รันไฟล์ `run_remote.sh.bat` (รองรับการรันผ่าน Wine บนระบบ Linux) 
*  **Linux**: รันคำสั่ง `bash run_remote.sh` 

**ความสามารถของสคริปต์รันโปรแกรม:**
*  **Dependency Check**: ตรวจสอบและติดตั้ง Python Library (requests, playwright, beautifulsoup4, ฯลฯ) ให้อัตโนมัติ 
*  **Browser Setup**: ตรวจสอบและติดตั้ง Chromium สำหรับใช้สแกนเว็บไซต์ 
*  **Logging**: บันทึก Log การทำงานลงในไฟล์ `script_run.log` เพื่อตรวจสอบย้อนหลัง 

---

## 📂 โครงสร้างไฟล์ที่สำคัญ

* `main.py`: สคริปต์หลักสำหรับการสแกนและดาวน์โหลด
* `remote_control.py`: สคริปต์สำหรับควบคุมบอทผ่าน Telegram
* `config.json`: ไฟล์เก็บค่าคอนฟิกทั้งหมด (User, Pass, Tokens, Settings)
* `seen.txt` / `hash_seen.txt`: ไฟล์ฐานข้อมูลประวัติเพื่อป้องกันการโหลดไฟล์ซ้ำ
* `manage_config.bat` / `manage_config.sh`: เครื่องมือตั้งค่าผ่านเมนูตัวเลือก 
* `run_autopilot.bat` / `run_autopilot.sh`: สคริปต์สำหรับเริ่มต้นระบบและติดตั้งส่วนเสริมอัตโนมัติ 
* `script_run.log`: ไฟล์เก็บประวัติการทำงานของบอทและข้อผิดพลาดต่าง ๆ 

---

## ⚠️ ข้อควรระวัง (Disclaimer)
โปรแกรมนี้สร้างขึ้นเพื่อช่วยอำนวยความสะดวกในการบริหารจัดการข้อมูลส่วนบุคคล ผู้ใช้งานควรตั้งค่าความถี่ในการสแกน (`MIN_WAIT_MINUTES`) ให้เหมาะสม เพื่อไม่ให้เป็นการรบกวนการทำงานของเซิร์ฟเวอร์เว็บไซต์ต้นทาง

---

## 📝 License
Distributed under the **MIT License**. See `LICENSE` for more information.

---
**Developed with ❤️ for the BearBit Community.**
