import os
import sys
import argparse
import pexpect
from dotenv import load_dotenv

load_dotenv(".env")

def _create_env_docker(filename):
    with open(filename, 'r') as file:
        lines = file.readlines()

    docker_lines = [line.strip() for line in lines if line.strip() and not line.startswith('#')]
    docker_content = '\n'.join([line.replace('"', '') for line in docker_lines])

    with open('.env-docker', 'w') as docker_file:
        docker_file.write(docker_content)
    print('.env-docker file created!')

def initialize_dvm():
    private_key = os.getenv("PK")
    network_id = os.getenv("NETWORK_ID")
    acc_pwd = os.getenv("ACC_PWD", "")
    acc_name = os.getenv("ACC_NAME", "DVM-DOCKER-ACCOUNT")

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

def build():
    telliot_branch = os.getenv("TELLIOT_BRANCH")

    if not telliot_branch:
        print("TELLIOT_BRANCH env var not found")
        exit(1)

    build_command = f"docker build --build-arg TELLIOT_BRANCH={telliot_branch} -t dvm:dockerfile ."
    os.system(build_command)

    _create_env_docker('.env')

    run_command = "docker run --env-file .env-docker -it dvm:dockerfile"
    os.system(run_command)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize DVM Docker")
    parser.add_argument("--mode", type=str, help="Mode to run the script", default="build")

    args = parser.parse_args()

    if args.mode == "build":
        print("Building DVM Docker")
        build()

    if args.mode == "initialize":
        print("Initializing DVM Docker")
        initialize_dvm()
