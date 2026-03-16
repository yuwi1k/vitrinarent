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
    # Check order from the actual search page
    "cd /root/vitrinarent && curl -s http://localhost:8000/search -H 'Host: aodiapazon.ru' | grep -oP 'building-group__title.*?</h3>' | head -10",
    # Check DB order
    "cd /root/vitrinarent && docker compose exec -T -e PGPASSWORD=postgres db psql -U postgres -d vitrina_db -c \"SELECT id, sort_order, parent_id, substring(title for 40) as title FROM properties ORDER BY sort_order, id DESC;\"",
    # Check logs for errors
    "cd /root/vitrinarent && docker compose logs app --tail 5 2>&1 | grep -i error || echo 'no errors'",
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    print(out)
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        print("STDERR:", err[:300])

ssh.close()
print("Done!")
