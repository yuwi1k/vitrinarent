import paramiko

HOST = "109.120.152.56"
PASSWORD = "MLDBVqwH1De1ZoTo"
REMOTE_PATH = "/root/vitrinarent/.env"
LOCAL_PATH = r"c:\vitrinarent\.env"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username="root", password=PASSWORD)

sftp = ssh.open_sftp()
sftp.put(LOCAL_PATH, REMOTE_PATH)
sftp.close()
print(">>> .env uploaded")

cmds = [
    "cd /root/vitrinarent && docker compose up -d --force-recreate app",
    "sleep 5",
    "curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/",
]
for cmd in cmds:
    print(f"\n>>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err:
        print(err)

ssh.close()
print("\nDone!")
