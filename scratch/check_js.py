import re
import subprocess

with open('app/templates/matches.html', 'r', encoding='utf-8') as f:
    html = f.read()

scripts = re.findall(r'<script>(.*?)</script>', html, flags=re.DOTALL)

for i, script in enumerate(scripts):
    with open(f'scratch/script_{i}.js', 'w', encoding='utf-8') as f:
        f.write(script)
    
    result = subprocess.run(['node', '-c', f'scratch/script_{i}.js'], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error in script {i}:")
        print(result.stderr)
    else:
        print(f"Script {i} is OK")
