import paramiko, time

HOST = "109.120.152.56"
PASSWORD = "MLDBVqwH1De1ZoTo"

for attempt in range(5):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(HOST, username="root", password=PASSWORD, timeout=15, banner_timeout=15)
        break
    except Exception as e:
        print(f"Attempt {attempt+1} failed: {e}")
        time.sleep(5)
else:
    print("All SSH attempts failed")
    exit(1)

cmds = [
    "cd /root/vitrinarent && git log --oneline -3",
    "cd /root/vitrinarent && git diff HEAD -- static/diapazon/css/diapazon-asset.css | head -40",
    "grep -c 'flex-direction: column' /root/vitrinarent/static/diapazon/css/diapazon-asset.css",
    "grep -n 'building-group__header' /root/vitrinarent/static/diapazon/css/diapazon-asset.css",
    "sed -n '2046,2060p' /root/vitrinarent/static/diapazon/css/diapazon-asset.css",
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err.strip():
        print(err)

ssh.close()
print("Done!")
