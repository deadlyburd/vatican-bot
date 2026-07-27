with open('backend/telegram_bot.py','r',encoding='utf-8') as f:
    content = f.read()
content = content.replace('reply_markup=kb_times()', 'reply_markup=kb_times(ud.get("selected_times",[]))')
with open('backend/telegram_bot.py','w',encoding='utf-8') as f:
    f.write(content)
print('Done')
