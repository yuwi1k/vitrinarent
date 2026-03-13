import paramiko

HOST = "109.120.152.56"
PASSWORD = "MLDBVqwH1De1ZoTo"

commands = [
    "cd /root/vitrinarent && git pull",
    "cd /root/vitrinarent && docker compose up -d --build --force-recreate app",
    "sleep 10",
    "cd /root/vitrinarent && docker compose exec -T db psql -U postgres -c \"ALTER USER postgres PASSWORD 'postgres';\"",
    "sleep 3",
    "cd /root/vitrinarent && docker compose exec -T app alembic upgrade head",
    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/",
]

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username="root", password=PASSWORD, timeout=15)

for cmd in commands:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=180)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.strip())
    if err.strip():
        print(err.strip())
    if code != 0:
        print(f"[exit code: {code}]")

client.close()
print("\nDone!")
