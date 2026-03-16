import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("109.120.152.56", username="root", password="MLDBVqwH1De1ZoTo")

cmds = [
    ('diapazon favicon', 'curl -s -o /dev/null -w "%{http_code}" -H "Host: aodiapazon.ru" http://localhost:8000/favicon.ico'),
    ('diapazon favicon headers', 'curl -s -I -H "Host: aodiapazon.ru" http://localhost:8000/favicon.ico 2>&1 | head -5'),
    ('external favicon', 'curl -s -o /dev/null -w "%{http_code}" https://aodiapazon.ru/favicon.ico'),
]

for label, cmd in cmds:
    _, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode().strip()
    print(f"[{label}] {out}")

c.close()
