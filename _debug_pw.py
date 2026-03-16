import paramiko

HOST = "109.120.152.56"
PASSWORD = "MLDBVqwH1De1ZoTo"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username="root", password=PASSWORD)

cmds = [
    "docker compose exec -T app env | grep ADMIN",
    "docker compose exec -T app python -c \"import os; print('ADMIN_PASSWORD env:', repr(os.getenv('ADMIN_PASSWORD')))\"",
    "docker compose exec -T app python -c \"import os; f='data/.admin_password'; print('file exists:', os.path.isfile(f)); open(f) and print('content:', open(f).read()[:80]) if os.path.isfile(f) else None\"",
    "docker compose exec -T app find / -name '.admin_password' 2>/dev/null || true",
    "cat /root/vitrinarent/.env | grep ADMIN",
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(f"cd /root/vitrinarent && {cmd}", timeout=30)
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err.strip():
        print("STDERR:", err)

ssh.close()
