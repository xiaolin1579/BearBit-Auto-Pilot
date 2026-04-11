@echo off
title BearBit Config Manager (Full System)
setlocal enabledelayedexpansion

:menu
cls
echo ======================================================
echo    BearBit Config Manager (Press Enter to Skip)
echo ======================================================
echo  1) Setup Account
echo  2) Notification
echo  3) Filter Settings
echo  4) Global Auto-Clean Settings
echo  5) Node Management
echo  6) Exit
echo ======================================================
set /p choice="Select [1-6]: "

if "%choice%"=="1" goto account
if "%choice%"=="2" goto notify
if "%choice%"=="3" goto filter
if "%choice%"=="4" goto global_clean
if "%choice%"=="5" goto node
if "%choice%"=="6" exit
goto menu

:account
cls
echo --- Account Setup ---
set "u=" & set /p u="Username: "
set "p=" & set /p p="Password: "
python -c "import json; d=json.load(open('config.json', encoding='utf-8')); if '%u%': d['BEARBIT']['username']='%u%'; if '%p%': d['BEARBIT']['password']='%p%'; json.dump(d, open('config.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)"
goto menu

:notify
cls
echo --- Notification ---
set "t_en=" & set /p t_en="Enable Telegram (true/false): "
set "t_token=" & set /p t_token="Bot Token: "
set "t_id=" & set /p t_id="Chat ID: "
python -c "import json; d=json.load(open('config.json', encoding='utf-8')); c=d['TELEGRAM_CONFIG']; if '%t_en%': c['notify_enable']=(True if '%t_en%'.lower()=='true' else False); if '%t_token%': c['main_bot_token']='%t_token%'; if '%t_id%': c['chat_id']='%t_id%'; json.dump(d, open('config.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)"
goto menu

:filter
cls
echo --- Filter Settings ---
set "MIN_S=" & set /p MIN_S="Min Size (GB) [Enter to skip]: "
set "MAX_S=" & set /p MAX_S="Max Size (GB) [Enter to skip]: "
set "F_EN=" & set /p F_EN="Enable Freeload? (y/n): "
set "F_VAL=0"
if /i "%F_EN%"=="y" (
    set /p F_VAL="Min Free %% (e.g. 50): "
)

:: ใช้เทคนิค os.environ เพื่อดึงค่าจาก Batch อย่างปลอดภัย
python -c "import json, os; d=json.load(open('config.json', encoding='utf-8')); s=d['SETTING']; m_s=os.getenv('MIN_S'); m_a=os.getenv('MAX_S'); f_e=os.getenv('F_EN'); f_v=os.getenv('F_VAL'); s['MIN_SIZE_GB']=float(m_s) if m_s else s.get('MIN_SIZE_GB', 15.0); s['MAX_SIZE_GB']=float(m_a) if m_a else s.get('MAX_SIZE_GB', 150.0); s['FREELOAD_ENABLE']=(True if f_e.lower()=='y' else False) if f_e else s.get('FREELOAD_ENABLE', True); s['MIN_FREE_PERCENT']=int(f_v) if f_v!='0' else s.get('MIN_FREE_PERCENT', 0); json.dump(d, open('config.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)"

echo.
echo ✅ Update Complete!
pause
goto menu

:global_clean
cls
echo --- Global Clean Settings ---
set /p g_en="Enable Global Clean (true/false): "
set /p g_ratio="Min Ratio: "
set /p g_min_t="Min Seeding Time (Min): "
set /p g_max_t="Max Seeding Time (Min): "
python -c "import json; d=json.load(open('config.json', encoding='utf-8')); g=d.get('GLOBAL_CLEAN', {}); g['enable']=(True if '%g_en%'.lower()=='true' else False) if '%g_en%' else g.get('enable', True); g['min_ratio']=float('%g_ratio%') if '%g_ratio%' else g.get('min_ratio', 1.0); g['min_time']=int('%g_min_t%') if '%g_min_t%' else g.get('min_time', 360); g['max_time']=int('%g_max_t%') if '%g_max_t%' else g.get('max_time', 1440); d['GLOBAL_CLEAN']=g; json.dump(d, open('config.json', 'w', encoding='utf-8'), indent=2)"
goto menu

:node
cls
echo --- Node Management ---
python -c "import json; d=json.load(open('config.json', encoding='utf-8')); [print(f'{i}: {n[\"name\"]} (Clean: {n.get(\"clean_settings\", {}).get(\"enable\")})') for i, n in enumerate(d.get('NODES', []))]"
set /p op="a) Add | e) Edit | d) Delete | b) Back: "
if "%op%"=="a" goto node_add
if "%op%"=="e" goto node_edit
if "%op%"=="d" goto node_del
goto menu

:node_add
set /p n_name="Name: "
set /p n_type="Type (qbit/rtorrent): "
set /p n_url="URL: "
set /p n_user="User: "
set /p n_pass="Pass: "
set /p n_quota="Quota (GB): "
set /p n_nginx="Nginx Auth (true/false): "
set /p nc_en="Enable Node Clean (true/false): "
python -c "import json; d=json.load(open('config.json', encoding='utf-8')); d['NODES'].append({'name':'%n_name%','type':'%n_type%','url':'%n_url%','qb_user':'%n_user%','qb_pass':'%n_pass%','rt_user':'%n_user%','rt_pass':'%n_pass%','quota_gb':float('%n_quota%' or 0),'nginx':(True if '%n_nginx%'.lower()=='true' else False),'enable':True,'clean_settings':{'enable':(True if '%nc_en%'.lower()=='true' else False),'min_ratio':0.5,'min_time':360.0,'max_time':720.0}}); json.dump(d, open('config.json', 'w', encoding='utf-8'), indent=2)"
goto menu

:node_edit
set /p idx="Enter Index to Edit: "
echo --- Editing Node %idx% ---
set /p n_name="Name: "
set /p n_url="URL: "
set /p n_user="User: "
set /p n_pass="Pass: "
set /p n_quota="Quota (GB): "
set /p n_nginx="Nginx Auth (true/false): "
set /p nc_en="Enable Node Clean (true/false): "
python -c "import json; d=json.load(open('config.json', encoding='utf-8')); n=d['NODES'][%idx%]; n['name']='%n_name%' or n['name']; n['url']='%n_url%' or n['url']; if '%n_user%': n['qb_user']=n['rt_user']='%n_user%'; if '%n_pass%': n['qb_pass']=n['rt_pass']='%n_pass%'; n['quota_gb']=float('%n_quota%') if '%n_quota%' else n['quota_gb']; n['nginx']=(True if '%n_nginx%'.lower()=='true' else False) if '%n_nginx%' else n.get('nginx', True); cs=n.get('clean_settings', {'enable':False, 'min_ratio':0.5, 'min_time':360.0, 'max_time':720.0}); cs['enable']=(True if '%nc_en%'.lower()=='true' else False) if '%nc_en%' else cs['enable']; n['clean_settings']=cs; json.dump(d, open('config.json', 'w', encoding='utf-8'), indent=2)"
goto menu

:node_del
set /p idx="Enter Index to Delete: "
python -c "import json; d=json.load(open('config.json', encoding='utf-8')); d['NODES'].pop(%idx%); json.dump(d, open('config.json', 'w', encoding='utf-8'), indent=2)"
goto menu