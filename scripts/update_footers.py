import os
import glob
import re

app_dir = r"c:\Users\Delstaford\Desktop\mmust-dating-ai\mmust-dating-ai\app"
files_to_check = glob.glob(os.path.join(app_dir, "**", "*.py"), recursive=True)

footer_target_1 = re.compile(r"FIND YOUR MATCH AI(\s*Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence \.)?", re.IGNORECASE)

footer_target_2 = re.compile(r"&copy; \{datetime\.now\(\)\.year\} Delstarford Works\. All rights reserved\.")
footer_target_3 = re.compile(r"FIND YOUR MATCH AI Powered Dating")

replacement = "FIND YOUR MATCH AI | Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence ."

for filepath in files_to_check:
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # We want to replace specific HTML footers. Let's be careful.
    # It's better to just replace the inner text of the footer tags.
    # The user specifically mentioned: "FIND YOUR MATCH     Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence ."
    
    content = content.replace("Delstarford Works. All rights reserved.", "Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence .")
    
    # In main.py, v3/auth.py, and auth.py we have OTP emails.
    content = content.replace(">FIND YOUR MATCH AI<", ">FIND YOUR MATCH AI | Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence .<")
    content = content.replace("FIND YOUR MATCH AI Powered Dating", "FIND YOUR MATCH AI | Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence .")
    
    if original != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Updated {filepath}")
