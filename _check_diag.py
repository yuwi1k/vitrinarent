import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("109.120.152.56", username="root", password="MLDBVqwH1De1ZoTo")

cmds = [
    ('favicon status', 'curl -s -o /dev/null -w "%{http_code}" -H "Host: aodiapazon.ru" http://localhost:8000/favicon.ico'),
    ('favicon content-type', 'curl -s -I -H "Host: aodiapazon.ru" http://localhost:8000/favicon.ico | grep -i content-type'),
    ('sitemap status', 'curl -s -o /dev/null -w "%{http_code}" -H "Host: aodiapazon.ru" http://localhost:8000/sitemap.xml'),
    ('sitemap head', 'curl -s -H "Host: aodiapazon.ru" http://localhost:8000/sitemap.xml | head -5'),
    ('favicon external', 'curl -s -o /dev/null -w "%{http_code}" https://aodiapazon.ru/favicon.ico'),
    ('favicon ext headers', 'curl -s -I https://aodiapazon.ru/favicon.ico | head -10'),
]

for label, cmd in cmds:
    _, stdout, stderr = c.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    print(f"[{label}]")
    print(out or err or "(empty)")
    print()

c.close()
