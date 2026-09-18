import sys

with open('c:/Users/Delstaford/Desktop/mmust-dating-ai/app/main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

with open('c:/Users/Delstaford/Desktop/mmust-dating-ai/app/api_chat_replacement.py', 'r', encoding='utf-8') as f:
    replacement = f.read()

start = -1
end = -1
for i, line in enumerate(lines):
    if 'WEBSOCKETS (CHAT, AI COMPANION' in line:
        start = i
    if '@app.route(\'/discover\')' in line:
        end = i - 1
        break

if start != -1 and end != -1:
    new_lines = lines[:start] + [replacement + "\n"] + lines[end:]
    with open('c:/Users/Delstaford/Desktop/mmust-dating-ai/app/main.py', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print(f"Successfully replaced lines {start} to {end}.")
else:
    print(f"Could not find markers. Start: {start}, End: {end}")
