#!/bin/bash

GREEN='\033[0;32m'
NC='\033[0m'
CONFIG_FILE="config.json"

# ฟังก์ชันดึงค่าจาก JSON
get_val() {
    python3 -c "import json, os; d=json.load(open('$CONFIG_FILE')) if os.path.exists('$CONFIG_FILE') else {}; print(d$1)" 2>/dev/null || echo "0"
}

update_json() {
    python3 -c "
import json, os
with open('$CONFIG_FILE', 'r', encoding='utf-8') as f:
    d = json.load(f)
$1
with open('$CONFIG_FILE', 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
"
}

while true; do
    clear
    echo "======================================================"
    echo "       BearBit Config Manager (Full System)"
    echo "======================================================"
    echo "1) Setup Account"
    echo "2) Notification"
    echo "3) Filter Settings"
    echo "4) Global Clean Settings"
    echo "5) Node Management"
    echo "6) Exit"
    echo "======================================================"
    read -p "Select [1-6]: " choice

    case $choice in
        1)
            read -p "Username: " u; read -p "Password: " p
            export U_VAL="$u" P_VAL="$p"
            update_json "
u=os.getenv('U_VAL'); p=os.getenv('P_VAL')
if u: d['BEARBIT']['username']=u
if p: d['BEARBIT']['password']=p" ;;

2)
            while true; do
                echo "--- Notification Settings ---"
                echo "1) Telegram Config"
                echo "2) LINE Config"
                echo "3) Discord Config"
                echo "4) Back to Main Menu"
                read -p "Select provider: " notify_opt
                
                case $notify_opt in
1)
                        echo "[ Telegram Configuration ]"
                        # --- ส่วน Notify ---
                        read -p "   Notify Enable (true/false, Enter to skip): " t_en
                        if [[ "$t_en" == "true" ]]; then
                            read -p "   Main Bot Token: " t_token
                            read -p "   Chat ID: " t_id
                        elif [[ "$t_en" == "false" ]]; then
                            t_token=""
                            t_id=""
                        fi

                        # --- ส่วน Remote Control ---
                        echo "   --- Remote Control ---"
                        read -p "   Remote Enable (true/false, Enter to skip): " r_en
                        if [[ "$r_en" == "true" ]]; then
                            read -p "   Remote Bot Token: " r_token
                        elif [[ "$r_en" == "false" ]]; then
                            r_token=""
                        fi
                        
                        export T_EN="$t_en" T_TO="$t_token" T_ID="$t_id" \
                               R_EN="$r_en" R_TO="$r_token"
                               
                        update_json "
c=d['TELEGRAM_CONFIG']
v_en, v_to, v_id = os.getenv('T_EN'), os.getenv('T_TO'), os.getenv('T_ID')
v_ren, v_rto = os.getenv('R_EN'), os.getenv('R_TO')

# อัปเดต Main Notify
if v_en and v_en.strip():
    c['notify_enable'] = (v_en.lower() == 'true')
    # ถ้าตั้งเป็น true และมีการกรอก token/id มาใหม่ถึงจะทับค่าเดิม
    if v_to: c['main_bot_token'] = v_to
    if v_id: c['chat_id'] = v_id

# อัปเดต Remote Control
if v_ren and v_ren.strip():
    c['remote_enable'] = (v_ren.lower() == 'true')
    # ถ้าตั้งเป็น true และมีการกรอก remote token มาใหม่ถึงจะทับค่าเดิม
    if v_rto: c['remote_bot_token'] = v_rto"
                        echo "✅ Telegram & Remote updated."
                        ;;
					2)
                        echo "[ LINE Configuration ]"
                        read -p "   Enable (true/false, Enter to skip): " l_en
                        # Logic: true ถามต่อ / false ข้าม
                        if [[ "$l_en" == "true" ]]; then
                            read -p "   Access Token: " l_token
                        elif [[ "$l_en" == "false" ]]; then
                            l_token=""
                        fi

                        export L_EN="$l_en" L_TO="$l_token"
                        
                        update_json "
c=d['LINE_CONFIG']
v_en, v_to = os.getenv('L_EN'), os.getenv('L_TO')

if v_en and v_en.strip():
    c['enable'] = (v_en.lower() == 'true')
    # อัปเดต token เฉพาะเมื่อมีการกรอกค่าใหม่มาเท่านั้น
    if v_to: c['access_token'] = v_to
"
                        echo "✅ LINE updated."
                        ;;
3)
                        echo "[ Discord Configuration ]"
                        read -p "   Enable (true/false, Enter to skip): " d_en
                        
                        if [[ "$d_en" == "true" ]]; then
                            read -p "   Webhook URL: " d_url
                            read -p "   Admin User ID to Mention (Enter to skip): " d_admin
                        elif [[ "$d_en" == "false" ]]; then
                            d_url=""
                            d_admin=""
                        fi

                        export D_EN="$d_en" D_URL="$d_url" D_ADMIN="$d_admin"
                        
                        update_json "
c=d['DISCORD_CONFIG']
v_en, v_url, v_admin = os.getenv('D_EN'), os.getenv('D_URL'), os.getenv('D_ADMIN')

if v_en and v_en.strip():
    c['enable'] = (v_en.lower() == 'true')
    if v_url: c['webhook_url'] = v_url
    if v_admin: c['admin_id'] = v_admin
"
                        echo "✅ Discord updated."
                        ;;
                    4) break ;;
                    *) echo "Invalid option" ;;
                esac
                echo ""
            done
            ;;

		3)
            mi=$(get_val "['SETTING'].get('MIN_SIZE_GB', 15.0)")
            ma=$(get_val "['SETTING'].get('MAX_SIZE_GB', 150.0)")
            read -p "Min Size (GB) [$mi]: " n_mi
            read -p "Max Size (GB) [$ma]: " n_ma
            read -p "Enable Freeload? (y/n): " f_en
            f_val="0"
            [[ "$f_en" == "y" ]] && read -p "Min Free %: " f_val
            export MI="${n_mi:-$mi}" MA="${n_ma:-$ma}" F_EN="$f_en" F_VAL="$f_val"
            update_json "
s=d['SETTING']
s['MIN_SIZE_GB']=float(os.getenv('MI'))
s['MAX_SIZE_GB']=float(os.getenv('MA'))
if os.getenv('F_EN'): s['FREELOAD_ENABLE']=(True if os.getenv('F_EN')=='y' else False)
if os.getenv('F_VAL')!='0': s['MIN_FREE_PERCENT']=int(os.getenv('F_VAL'))"
            echo -e "${GREEN}✅ Update Filter Success!${NC}"; sleep 1 ;;

        4)
            read -p "Global Clean Enable (true/false): " g_en; read -p "Min Ratio: " g_r; read -p "Min Time: " g_mi; read -p "Max Time: " g_ma
            export G_EN="$g_en" G_R="$g_r" G_MI="$g_mi" G_MA="$g_ma"
            update_json "
g=d.get('GLOBAL_CLEAN', {})
if os.getenv('G_EN'): g['enable']=(True if os.getenv('G_EN').lower()=='true' else False)
if os.getenv('G_R'): g['min_ratio']=float(os.getenv('G_R'))
if os.getenv('G_MI'): g['min_time']=int(os.getenv('G_MI'))
if os.getenv('G_MA'): g['max_time']=int(os.getenv('G_MA'))
d['GLOBAL_CLEAN']=g" ;;

		5)
            echo "--- Node Management ---"
            # ส่วนที่เพิ่ม: แสดงรายชื่อ Node ปัจจุบันทันทีที่เข้าเมนู
            echo "📋 Current Nodes:"
            python3 -c "
import json, os
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        nodes = data.get('NODES', [])
        if not nodes:
            print('   (No nodes configured)')
        for i, n in enumerate(nodes, 1):
            status = '🟢' if n.get('enable', True) else '🔴'
            print(f'   {i}. {status} Name: {n[\"name\"]} | Type: {n[\"type\"]} | Quota: {n.get(\"quota_gb\", 0)}GB')
except Exception as e:
    print(f'   Error reading nodes: {e}')
"
            echo "-----------------------"
            echo "1) Add New Node"
            echo "2) Edit Node (by Name)"
            echo "3) Delete Node (by Name)"
            echo "4) Clear All Nodes"
            read -p "Select option: " node_opt
            
            case $node_opt in
                1)
                    # --- ADD NODE ---
                    read -p "Node Name: " n_name
                    read -p "Type (qbit/rtorrent): " n_type
                    read -p "WebUI URL: " n_url
                    read -p "Username: " n_user
                    read -p "Password: " n_pass
                    read -p "Quota GB (0=unlimited): " n_quota
                    read -p "Nginx Auth (true/false): " n_nginx

                    export N_NAME="$n_name" N_TYPE="$n_type" N_URL="$n_url" N_USER="$n_user" N_PASS="$n_pass" N_QUOTA="$n_quota" N_NGINX="$n_nginx"
                    
                    update_json "
new_node = {
    'name': os.getenv('N_NAME'),
    'type': os.getenv('N_TYPE'),
    'url': os.getenv('N_URL'),
    'quota_gb': float(os.getenv('N_QUOTA') or 0),
    'nginx': True if os.getenv('N_NGINX').lower() == 'true' else False,
    'enable': True,
    'clean_settings': {'enable': True, 'min_ratio': 0.5, 'min_time': 120, 'max_time': 720}
}
if os.getenv('N_TYPE') == 'rtorrent':
    new_node.update({'rt_user': os.getenv('N_USER'), 'rt_pass': os.getenv('N_PASS')})
else:
    new_node.update({'qb_user': os.getenv('N_USER'), 'qb_pass': os.getenv('N_PASS')})
d['NODES'].append(new_node)"
                    echo "✅ Added node: $n_name" ;;

				2)
                    # --- EDIT NODE ---
                    read -p "Enter Node Name to Edit: " edit_name
                    # ถ้าเว้นว่างส่วนนี้จะข้ามการแก้ไขฟิลด์นั้นๆ
                    read -p "New Quota GB (Leave blank to keep current): " e_quota
                    read -p "Enable Node true/false (Leave blank to keep current): " e_en
                    
                    export E_NAME="$edit_name" E_QUOTA="$e_quota" E_EN="$e_en"
                    
                    update_json "
target_found = False
for node in d['NODES']:
    if node['name'] == os.getenv('E_NAME'):
        target_found = True
        # ตรวจสอบว่ามีการกรอกค่าใหม่มาหรือไม่ (ถ้าไม่ว่างถึงจะทับค่าเดิม)
        new_quota = os.getenv('E_QUOTA')
        if new_quota and new_quota.strip():
            node['quota_gb'] = float(new_quota)
            
        new_en = os.getenv('E_EN')
        if new_en and new_en.strip():
            node['enable'] = (new_en.lower() == 'true')
            
        print(f'✅ Updated node: {node[\"name\"]}')
if not target_found:
    print('❌ Node not found!')
" ;;
                3)
                    # --- DELETE NODE ---
                    read -p "Enter Node Name to Delete: " del_name
                    export DEL_NAME="$del_name"
                    update_json "d['NODES'] = [n for n in d['NODES'] if n['name'] != os.getenv('DEL_NAME')]"
                    echo "🗑️ Deleted node: $del_name" ;;

                4)
                    # --- CLEAR ALL ---
                    read -p "Clear all nodes? (y/n): " confirm
                    [[ "$confirm" == "y" ]] && update_json "d['NODES'] = []" && echo "🗑️ All nodes cleared." ;;

                *) echo "Invalid option" ;;
            esac
            ;;
        6) exit ;;
    esac
done