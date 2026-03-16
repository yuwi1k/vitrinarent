import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("109.120.152.56", username="root", password="MLDBVqwH1De1ZoTo")

_, stdout, _ = c.exec_command('curl -s -H "Host: aodiapazon.ru" http://localhost:8000/ | grep -i metrika')
out = stdout.read().decode().strip()
print("[metrika in HTML]")
print(out if out else "(NOT FOUND)")

print()

_, stdout, _ = c.exec_command('curl -s -H "Host: aodiapazon.ru" http://localhost:8000/ | grep -i "107710253"')
out = stdout.read().decode().strip()
print("[counter ID 107710253]")
print(out if out else "(NOT FOUND)")

print()

_, stdout, _ = c.exec_command('curl -s https://aodiapazon.ru/ | grep -i "107710253"')
out = stdout.read().decode().strip()
print("[external counter check]")
print(out if out else "(NOT FOUND)")

print()

_, stdout, _ = c.exec_command('curl -s https://aodiapazon.ru/ | head -15')
out = stdout.read().decode().strip()
print("[first 15 lines of HTML]")
print(out)

c.close()
