with open('backend/local_browser_agent.py','r', encoding='utf-8') as f:
    content = f.read()

replacements = [
    ("PROFILE['first_name']", "profile_data['first_name']"),
    ("PROFILE['last_name']", "profile_data['last_name']"),
    ("PROFILE['email']", "profile_data['email']"),
    ("PROFILE['phone']", "profile_data['phone']"),
    ("PROFILE['city']", "profile_data['city']"),
    ("PROFILE['country']", "profile_data['country']"),
    ("PROFILE['gender']", "profile_data['gender']"),
    ("PROFILE['birth_date']", "profile_data['birth_date']"),
    ("PROFILE['language']", "profile_data['language']"),
]
for old, new in replacements:
    content = content.replace(old, new)

with open('backend/local_browser_agent.py','w', encoding='utf-8') as f:
    f.write(content)
print('Done')
