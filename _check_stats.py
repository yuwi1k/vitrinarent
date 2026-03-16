import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("109.120.152.56", username="root", password="MLDBVqwH1De1ZoTo", timeout=15)

print(">>> Running collect_statistics with verbose logging...")
cmd = '''cd /root/vitrinarent && docker compose exec -T app python -c "
import asyncio, logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(name)s: %(message)s')
from app.scheduler import scheduler_service
asyncio.run(scheduler_service.job_collect_statistics())
print('DONE')
" 2>&1'''
stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
out = stdout.read().decode('utf-8', errors='replace').strip()
err = stderr.read().decode('utf-8', errors='replace').strip()
if out: print(out[-5000:])
if err: print(err[-5000:])

print("\n>>> Checking stats_data...")
cmd2 = '''cd /root/vitrinarent && docker compose exec -T db psql -U postgres -d vitrina_db -t -c "SELECT id, stats_data FROM properties LIMIT 5;"'''
stdin, stdout, stderr = client.exec_command(cmd2, timeout=30)
print(stdout.read().decode('utf-8', errors='replace').strip())

client.close()
print("\nDone!")
