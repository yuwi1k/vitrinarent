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
    # Check security headers
    "curl -sI https://aodiapazon.ru/ 2>/dev/null | grep -iE 'strict-transport|x-frame|x-content-type|referrer-policy|permissions-policy'",
    # Check /docs disabled
    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/docs",
    # Check /openapi.json disabled
    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/openapi.json",
    # Check health endpoint doesn't leak details
    "cd /root/vitrinarent && docker compose exec -T app python -c 'import requests; print(requests.get(\"http://localhost:8000/health/readiness\").json())' 2>&1 || curl -s http://localhost:8000/health/readiness",
    # Check ENVIRONMENT
    "cd /root/vitrinarent && grep ENVIRONMENT .env",
    # Check DB port not exposed
    "cd /root/vitrinarent && docker compose ps --format '{{.Ports}}' db 2>/dev/null || docker compose ps db",
    # Check container user
    "cd /root/vitrinarent && docker compose exec -T app whoami",
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
