import os
import sys
from dotenv import load_dotenv
import pexpect

load_dotenv()

private_key = os.getenv("PK")
network_id = os.getenv("NETWORK_ID")
acc_pwd = os.getenv("ACC_PWD", "")
acc_name = os.getenv("ACC_NAME", "DVM-ACCOUNT")

if not private_key:
    print("PK env var not found")
    exit(1)

if not network_id:
    print("NETWORK_ID env var not found")
    exit(1)

cli_process = pexpect.spawn('sh', encoding='utf8', timeout=None)
cli_process.logfile_read = sys.stdout
cli_process.sendline(f'telliot account add {acc_name} {private_key} {network_id}')
result = cli_process.expect([f'Enter encryption password for {acc_name}:', f'Account {acc_name} already exists.'])
if result == 1:
    print('Account already exists!')
else:
    cli_process.sendline(acc_pwd)
    cli_process.expect(f'Confirm password:')
    cli_process.sendline(acc_pwd)
    print('Account Created!')

cli_process.sendline(f'cli -d -a {acc_name}')
cli_process.expect(f'Enter password for {acc_name} account: ')
cli_process.sendline(acc_pwd)
print('Account Unlocked!')
print('DVM Initialized!')
cli_process.expect(pexpect.EOF)
