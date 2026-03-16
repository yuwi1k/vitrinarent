import paramiko, sys
sys.stdout.reconfigure(encoding='utf-8')

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("109.120.152.56", username="root", password="MLDBVqwH1De1ZoTo", timeout=15)

print(">>> Testing check_errors_and_notify...")
cmd = '''cd /root/vitrinarent && docker compose exec -T app python -c "
import asyncio, logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
from app.scheduler import scheduler_service
asyncio.run(scheduler_service.job_check_errors_and_notify())
print('DONE')
" 2>&1'''
stdin, stdout, stderr = client.exec_command(cmd, timeout=120)
out = stdout.read().decode('utf-8', errors='replace').strip()
if out: print(out[-3000:])

client.close()
print("\nDone!")
