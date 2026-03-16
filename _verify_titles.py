import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("109.120.152.56", username="root", password="MLDBVqwH1De1ZoTo")

_, stdout, _ = c.exec_command('curl -s https://aodiapazon.ru/catalog/gab | grep -o "<title>[^<]*</title>"')
print("[diapazon gab title]", stdout.read().decode().strip())

_, stdout, _ = c.exec_command('curl -s -H "Host: xn----7sbfoma9adveqi.xn--p1ai" http://localhost:8000/catalog/gab | grep -o "<title>[^<]*</title>"')
print("[vitrina gab title]", stdout.read().decode().strip())

_, stdout, _ = c.exec_command('curl -s https://aodiapazon.ru/catalog/gab | grep "breadcrumbs"')
print("[diapazon breadcrumbs]", "FOUND" if stdout.read().decode().strip() else "NOT FOUND")

_, stdout, _ = c.exec_command('curl -s https://aodiapazon.ru/catalog/gab | grep "catalog-intro"')
print("[diapazon intro]", "FOUND" if stdout.read().decode().strip() else "NOT FOUND")

_, stdout, _ = c.exec_command('curl -s https://aodiapazon.ru/catalog/gab | grep "catalog-related"')
print("[diapazon related]", "FOUND" if stdout.read().decode().strip() else "NOT FOUND")

_, stdout, _ = c.exec_command('curl -s https://aodiapazon.ru/catalog/gab | grep "CollectionPage"')
print("[diapazon JSON-LD]", "FOUND" if stdout.read().decode().strip() else "NOT FOUND")

c.close()
