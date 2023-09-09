#!/bin/sh
pip install .

python -c "import telliot_core; print(f'telliot-core version installed - {telliot_core.__version__}')"
python -c "import telliot_feeds; print(f'telliot-feeds version installed - {telliot_feeds.__version__}')"

cd ../telliot-core
python3 change_address.py
cat ./src/telliot_core/data/contract_directory.json

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

#ADD CHAINED
expect_script=$(expect -c "
spawn chained add dvm \"$PK\" \"$NETWORK_ID\"
log_file expect_log.txt
expect \"Enter encryption password for dvm:\"
send \"\r\"
expect \"Confirm password:\"
send \"\r\"
expect eof
")

#RUN DVM
cd ../disputable-values-monitor
while true; do
    expect_script=$(expect -c '
        spawn cli -a dvm -d
        expect "Enter password for dvm account:"
        send "\r"
        expect eof
    ')

    echo "$expect_script"

    sleep 2
done