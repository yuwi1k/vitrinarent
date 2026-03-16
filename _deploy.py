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
    # Reset password again
    "cd /root/vitrinarent && docker compose exec -T db psql -U postgres -c \"ALTER USER postgres WITH PASSWORD 'postgres';\"",
    # Restart app
    "cd /root/vitrinarent && docker compose restart app",
    "sleep 5",
    "cd /root/vitrinarent && curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/",
    # Check actual page order
    "cd /root/vitrinarent && curl -s http://localhost:8000/search -H 'Host: aodiapazon.ru' | grep -oP 'building-group__title.*?</h3>'",
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=60)
    out = stdout.read().decode("utf-8", errors="replace")
    print(out)
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print("STDERR:", err[:300])

ssh.close()
print("\nDone!")
