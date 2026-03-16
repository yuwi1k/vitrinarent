import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("109.120.152.56", username="root", password="MLDBVqwH1De1ZoTo")

slugs = ["gab", "offices", "retail", "warehouses", "industrial", "buildings", "free-purpose"]

for host in ["aodiapazon.ru", "витрина-рент.рф"]:
    print(f"\n=== {host} ===")
    for slug in slugs:
        _, stdout, _ = c.exec_command(f'curl -s -o /dev/null -w "%{{http_code}}" -H "Host: {host}" http://localhost:8000/catalog/{slug}')
        code = stdout.read().decode().strip()
        _, stdout2, _ = c.exec_command(f'curl -s -H "Host: {host}" http://localhost:8000/catalog/{slug} | grep -o "<title>[^<]*</title>"')
        title = stdout2.read().decode().strip()
        print(f"  /catalog/{slug}: {code} | {title}")

print("\n=== Sitemap check (aodiapazon.ru) ===")
_, stdout, _ = c.exec_command('curl -s -H "Host: aodiapazon.ru" http://localhost:8000/sitemap.xml | grep catalog')
print(stdout.read().decode().strip()[:500])

c.close()
