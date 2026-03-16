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
    "cd /root/vitrinarent && docker compose exec -T -e PGPASSWORD=postgres db psql -U postgres -d vitrina_db -c \"SELECT id, sort_order, substring(title for 45) as title FROM properties WHERE parent_id IS NULL ORDER BY sort_order, id DESC;\"",
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out = stdout.read().decode("utf-8", errors="replace")
    print(out)

ssh.close()
print("Done!")
