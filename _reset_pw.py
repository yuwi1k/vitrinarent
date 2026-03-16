import paramiko

HOST = "109.120.152.56"
PASSWORD = "MLDBVqwH1De1ZoTo"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, username="root", password=PASSWORD)

cmds = [
    "docker compose exec -T app rm -f data/.admin_password",
    "docker compose exec -T app ls -la data/",
]
for cmd in cmds:
    print(f">>> {cmd}")
    stdin, stdout, stderr = ssh.exec_command(f"cd /root/vitrinarent && {cmd}", timeout=30)
    print(stdout.read().decode())
    err = stderr.read().decode()
    if err:
        print(err)

ssh.close()
print("Done! Password reset to .env value.")
