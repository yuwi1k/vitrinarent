import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("109.120.152.56", username="root", password="MLDBVqwH1De1ZoTo")

_, stdout, _ = c.exec_command('cd /root/vitrinarent && docker compose logs app --tail=30 2>&1 | grep -i favicon')
print("[favicon logs]")
print(stdout.read().decode())

_, stdout, _ = c.exec_command('cd /root/vitrinarent && docker compose exec -T app ls -la /app/static/diapazon/images/favicon*')
print("[favicon files in container]")
print(stdout.read().decode())

_, stdout, _ = c.exec_command('cd /root/vitrinarent && docker compose exec -T app ls -la /app/static/images/favicon*')
print("[vitrina favicon files]")
print(stdout.read().decode())

c.close()
