import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("109.120.152.56", username="root", password="MLDBVqwH1De1ZoTo", timeout=15)

checks = [
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/dashboard/login',
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/avito.xml',
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/cian.xml',
    'curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/',
    'cd /root/vitrinarent && docker compose logs app --tail=40 2>&1 | tail -40',
    'ls -la /root/vitrinarent/data/',
]
for cmd in checks:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out:
        print(out)
    if err:
        print(err)

client.close()
print("\nDone!")
