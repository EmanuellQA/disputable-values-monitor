#!/bin/bash
source .env
#source vars.example.sh
#
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
python expect.py
