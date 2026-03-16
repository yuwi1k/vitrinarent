import paramiko

HOST = "109.120.152.56"
PASSWORD = "MLDBVqwH1De1ZoTo"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username="root", password=PASSWORD)

cmds = [
    "cd /root/vitrinarent && git pull origin main",
    "cd /root/vitrinarent && docker compose down app && docker compose up -d app",
    "sleep 5",
    "cd /root/vitrinarent && curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/",
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err.strip():
        print(err)

ssh.close()
print("\nDone!")
