#!/bin/bash

python3 change_address.py
cat "/usr/local/lib/python3.10/site-packages/telliot_core/data/contract_directory.${ENV_NAME}.json"

#Set Volume Mounts as Environment Variable
token_file_path="/mnt/twilio-auth-token/dvm-${ENV_NAME}-twilio-auth-token"
sid_file_path="/mnt/twilio-account-sid/dvm-${ENV_NAME}-twilio-account-sid"
pk_file_path="/mnt/private-key/dvm-${ENV_NAME}-private-key"

token_file_contents=$(cat "$token_file_path")
sid_file_contents=$(cat "$sid_file_path")
pk_file_contents=$(cat "$pk_file_path")

export TWILIO_AUTH_TOKEN="$token_file_contents"
export TWILIO_ACCOUNT_SID="$sid_file_contents"
export PK="$pk_file_contents"

expect_script=$(expect -c "
spawn chained add dvm \"$PK\" \"$NETWORK_ID\"
log_file expect_log.txt
expect \"Enter encryption password for dvm:\"
send \"\r\"
expect \"Confirm password:\"
send \"\r\"
expect eof
")
echo "$expect_script" | expect
sleep 2
pip install pexpect
touch log.txt
python expect.py