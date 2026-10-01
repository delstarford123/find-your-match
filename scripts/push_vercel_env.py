import os
import subprocess

print("Pushing FIREBASE_CREDENTIALS...")
with open("firebase_key.json", "r") as f:
    cred_data = f.read()

process = subprocess.Popen(["vercel", "env", "add", "FIREBASE_CREDENTIALS", "production"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
stdout, stderr = process.communicate(input=cred_data)
if stdout: print(stdout.strip())
if stderr: print(stderr.strip())

print("Pushing .env variables...")
with open(".env", "r") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip("\"'")
        print(f"Pushing {key}...")
        proc = subprocess.Popen(["vercel", "env", "add", key, "production"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, shell=True)
        out, err = proc.communicate(input=value)
        if err: print(err.strip())
