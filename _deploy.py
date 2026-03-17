import paramiko, time, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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
    "cd /root/vitrinarent && git pull origin main",
    "cd /root/vitrinarent && grep -n 'lightbox__nav' static/diapazon/css/diapazon-asset.css | tail -10",
    "cd /root/vitrinarent && docker compose restart app",
    "sleep 5",
    "cd /root/vitrinarent && curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/",
    "cd /root/vitrinarent && docker compose exec -T app grep -n 'lightbox__nav' /app/static/diapazon/css/diapazon-asset.css | tail -10",
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=60)
    out = stdout.read().decode("utf-8", errors="replace")
    print(out)
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print("STDERR:", err[:500])

ssh.close()
print("\nDone!")
