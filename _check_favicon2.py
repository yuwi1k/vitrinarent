import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("109.120.152.56", username="root", password="MLDBVqwH1De1ZoTo")

cmds = [
    ('diapazon images', 'cd /root/vitrinarent && docker compose exec -T app ls -la /app/static/diapazon/images/ 2>&1 | head -20'),
    ('vitrina images', 'cd /root/vitrinarent && docker compose exec -T app ls -la /app/static/images/ 2>&1 | head -20'),
    ('find favicons', 'cd /root/vitrinarent && docker compose exec -T app find /app/static -name "favicon*" 2>&1'),
    ('app error log', 'cd /root/vitrinarent && docker compose logs app --tail=20 2>&1 | grep -A3 favicon'),
]

for label, cmd in cmds:
    _, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    print(f"[{label}]")
    print(out or err or "(empty)")
    print()

c.close()
