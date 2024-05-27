# Auto-disputer
A CLI dashboard & text alerts app for disputing bad values reported to Fetch oracles.

![](demo.gif)

## Introduction

Fetch is an active oracle protocol on Ethereum that allows users to accept off-chain data from a distribtued network of data reporters. Given that the Fetch team does not put data on chain for users themselves, users desire to be able to monitor and dispute bad data automatically. Hence, Fetch created the Auto-disputer, which monitors the accuracy of a group of feeds selected by the user, sends a text to the user if a feed becomes inaccurate, and disputes the bad data on-chain to protect the user's protocol from bad data.

## Using Twilio MockClient

1. Start the mock server by starting the docker container:
    ```sh
    docker compose up -d
    ```

2. Setup the `.env` file to use `MOCK_TWILIO` as "true":
    ```
    MOCK_TWILIO=true
    ```

By doing this configuration the DVM will set up the `alerts.py` module to use the MockClient server running on `http://127.0.0.1:4010` for Twilio. You can see the server logs by running `docker ps`, then look up for the container running the `stoplight/prism:4` image, the container name will probably include `disputable-values-monitor`, then run `docker logs <container-id>` -f.

## Quickstart

Configure environment variables:
```sh
cp .env.example .env
```

```
ENV_NAME=<default|dev|staging|preprod|prod>
NETWORK_ID=<369|943>
PK=<privatekey>
# Twilio
MOCK_TWILIO=true # uses the mock server for twilio
TWILIO_AUTH_TOKEN=
TWILIO_ACCOUNT_SID=
TWILIO_FROM="+1231231234"
ALERT_RECIPIENTS="+1231231234,+1231231234,+1231231234"

# AWS Simple Email Service (SES)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
AWS_SOURCE_EMAIL=user@example.com
AWS_DESTINATION_EMAILS="user1@example.com,user2@example.com"

# Telliot environment variables
PLS_SOURCE=weighted
PLS_CURRENCY_SOURCES=dai,usdc,plsx
PLS_ADDR_SOURCES="0xa2d510bf42d2b9766db186f44a902228e76ef262,0xb7f1f5a3b79b0664184bb0a5893aa9359615171b,0xFfd1fD891301D347ECaf4fC76866030387e97ED4"

COINGECKO_MOCK_URL=https://mock-price.fetchoracle.com/coingecko
PULSEX_SUBGRAPH_URL=https://graph.v4.testnet.pulsechain.com
FETCH_ADDRESS=0xb0f674d98ef8534b27a142ea2993c7b03bc7d649

# Slack
SLACK_WEBHOOK_HIGH="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
SLACK_WEBHOOK_MID="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
SLACK_WEBHOOK_LOW="https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
HIGH_ALERTS='["DISPUTE_AGAINST_REPORTER", "BEGAN_DISPUTE", "REMOVE_REPORT", "ALL_REPORTERS_STOP"]'
MID_ALERTS='["DISPUTABLE_REPORT", "REPORTER_STOP"]'
LOW_ALERTS='["REPORTER_BALANCE", "DISPUTER_BALANCE"]'

# list of services to send alerts
NOTIFICATION_SERVICE="sms,email,slack"

# list of reporters to monitor new disputes 
REPORTERS="0x0000000000000000000000000000000000000000,0x0000000000000000000000000000000000000000"
```

Note that to use the "sms" service in the `NOTIFICATION_SERVICE` service list requires a Twilio `.env` configuration, likewise, the "slack" service requires a SLACK_WEBHOOK_URL, and AWS SES environment config for the "email" service.

For the **Slack** notification service it's possible to configure different channels based on the urgency of the alert. For example, in the configuration above DVM will send "DISPUTE_AGAINST_REPORTER", "BEGAN_DISPUTE", "REMOVE_REPORT" and "ALL_REPORTERS_STOP" alerts to the slack webhook URL at `SLACK_WEBHOOK_HIGH`. If you want to make "BEGAN_DISPUTE" alert a mid alert for example, just move the "BEGAN_DISPUTE" item from `HIGH_ALERTS` to the `MID_ALERTS` list, in that way when DVM begins a dispute it will send this alert to `SLACK_WEBHOOK_MID` channel instead of `SLACK_WEBHOOK_HIGH`.

## Setup

### Prerequisites:
- Install Python 3.9
- Create an account on [twilio](https://www.twilio.com/docs/sms/quickstart/python)

## Install Locally

To install the dvm use the command below:

```bash!
./install.sh

```

After installing dvm, check if the venv is activated. If not, activate with the command below:

```bash!
source venv/bin/activate

```


## Install dockerize

To install the dvm use the command below:

```bash!
./install.sh

```

Build an image and run the image build

```bash!
docker build -t dvm .
docker run dvm
```


### Update environment variables:
```bash
cp vars.example.sh vars.sh
```
Edit `vars.sh`:
- List phone numbers you want alerts sent to (`ALERT_RECIPIENTS`).
- From [twilio](https://www.twilio.com/docs/sms/quickstart/python), specify the phone number that will send messages (`TWILIO_FROM`), your `TWILIO_ACCOUNT_SID`, and access key (`TWILIO_AUTH_TOKEN`).
- Export environment variables:
```
source vars.sh
```

### Edit the chains you want to monitor

To edit the chains you want to monitor:
1. Initialize telliot configuration
Run `telliot config init`

This will create a file called `~/telliot/endpoints.yaml`, where you can list and configure the chains and endpoints you want to monitor.
You will need a chain_id, network name, provider name, and a url for an endpoint. You must at least enter a mainnet endpoint, along with any other chains you want to monitor. You also must delete any chains you do not want to monitor.
Here is an example.
```
- type: RPCEndpoint # do not edit this line
  chain_id: 1
  network: mainnet # name of network
  provider: infura # name of provider
  url: myinfuraurl... # url for your endpoint
```

You can list as many chains as you'd like.

### Configuring Tresholds

Monitored Feeds and their Thresholds are defined in the `disputer-config.yaml` file. 

By default, the auto-disputer will monitor the ETH/USD feed on any chain id with a threshold Percentage threshold of 75%. In the default `dipsuter-config.yaml`, attached to the project, this is represented as:

```yaml
# AutoDisputer configuration file
feeds: # please reference https://github.com/fetch-io/dataSpecs/tree/main/types for examples of QueryTypes w/ Query Parameters
  - query_id: "0x83a7f3d48786ac2667503a61e8c415438ed2922eb86a2906e4ee66d9a2ce4992"
    threshold:
      type: Percentage
      amount: 0.75 # 75%

```

Where `0x83a7f3d48786ac2667503a61e8c415438ed2922eb86a2906e4ee66d9a2ce4992` represents the `queryId` of the eth/usd feed on Fetch. It is derived from the solidity code
```solidity
queryId = abi.encode("SpotPrice", abi.encode("eth", "usd"));
```

### Configuring thresholds for managed-feeds

The thresholds for Managed Price Feeds are configured in the `managed-feeds.yaml` file:
```yaml
# Managed feeds configuration file
managed_feeds:
  - query_id: "0x1f984b2c7cbcb7f024e5bdd873d8ca5d64e8696ff219ebede2374bf3217c9b75"
    datafeed_query_tag: "llpls-usd-spot"
    threshold:
      type: Percentage
      amount: 0.5
```

### FetchRNG and FetchRNGCustom:
In order to monitor feeds of types FetchRNG and FetchRNGCustom is required to setup the environment variables defined in 
vars.example.sh

Moreover, to define an FetchRNGCustom feed (managed or not) you can set it up in the disputer-config.yaml or managed-feeds.yaml 
using "Equality" as a threshold

# RNG Required
#export ETHERSCAN_API_KEY=

# FetchRNGCustom Required
#export ETHERSCAN_API_KEY=
#export INTERVAL=
#export START_TIME=
#export FETCH_RNG_NAME=

Additionally, for FetchRNG is required to setup the environment variable (in the .env file) DISPUTE_RNG_QUERIES="True" in order to start auto-disputes for these feeds.


A managed feed is identified by a `query_id`, it means a report with this queryId will be identified by DVM as a managed feed report. A managed feed report can be marked as a removable or a valid report, it is not marked as disputable.

Each managed feed needs a `datafeed_query_tag` and a `threshold` configuration.

- `datafeed_query_tag`: it setups which datafeed from telliot-feeds will be used to retrieved a trusted value price. In this case using `llpls-usd-spot` will use the [Pulse X PriceAggregator](https://github.com/fetchoracle/telliot-feeds/blob/dev/src/telliot_feeds/feeds/llpls_usd_feed.py) as datafeed, it retrieves the prices from the USDT, USDC and DAI Liquidity Pools and aggregates the prices using the weighted average algorithm to produce one final price.

- `threshold`: it setups the type of metric used to compare a reported value with a trusted value (fetched from telliot-feeds) and the amount of tolerance of difference between these values. The available options for `threshold.type` are `Percentage`, `Equality` and `Range`. The `threshold.amount` configures the tolerance of difference between the reported value and trusted value in decimals. For example, given a `Percentage` metric, a `threshold.amount` of `0.05` (5%), a reported value of `reported_val=7.582805765621e-05` and a trusted value of `trusted_val==7.545259339489967e-05`, the percentage change between these values is calculated as `(reported_val - trusted_val) / trusted_val = 0.0049761` (0.49761%), since 0.49% is within the tolerance of 5% the report price is evaluated as a valid price. 


### Usage:
```
cli -d
```

### Options
The available cli options are `-a`, `-av`, and `--wait`. You can use these options in any combination.

Use `-c` or `--confidence-threshold` to specify a universal percentage confidence threshold for monitoriting ONLY.

Use `-a` or `--account-name` to specify a `chained` account to use for disputing.
```bash
cli -a <your account name without quotes>
```

Use `-av` to get an alert for ALL `NewReport` events (regardless of whether they are disputable or not).
```bash
cli -av
```

Use `--wait` to set the wait time (in seconds) between event checks to reduce calls to the RPC endpoint. The default is seven seconds.
```bash
cli --wait 120
```

## How it works

The Auto-disputer is a complex event listener for any EVM chain, but specifically it listens for NewReport events on the Fetch network(s) the user wants to monitor.

When the Auto-disputer receives new NewReport events, it parses the reported value from the log, then compares the reported value to the trusted value from the Fetch reporter reference implementation, telliot.

In order to auto-dispute, users need to define what a "disputable value" is. To do this, users can set "thresholds" for feeds they want to monitor. Thresholds in the auto-disputer serve to set cutoffs between a healthy value and a disputable value. Users can pick from three types of thresholds: **range, percentage, and equality**.

### Range
**Range** -- if the difference between the reported value and the telliot value is greater than or equal to a set amount, dispute!

Ex. If the reported value is 250, and the telliot value is 1000, and the monitoring threshold is a range of 500, then the difference is 750 (it is >= to the range amount of 500), and the value is disputable! Therefore, a reported value of 501, in this case, would **not** be disputable. The smaller the range, the more strict the threshold.

### Percentage
**Percentage** -- if the difference between the telliot value and the reported value is greater than or equal to a set percentage of the telliot value, dispute! The smaller the percentage, the more strict the threshold.

Ex. If the reported value is 250, and the telliot value is 1000, and the percentage threshold is 0.50 (50%), then the percent difference is 75% of the telliot value (1000), and the value is disputable! Therefore, a reported value of 750, in this case, would **not** be disputable.

### Equality
**Equality** -- if there is any difference between the reported value and the telliot value, send a dispute!

Ex. If the reported value is "abc123", and the telliot value is "abc1234", then the value is disputable! However, to prevent false disputes due to checksummed addresses, the equality threshold sees "0xABC" and "0xabc" as equal.

## Considerations

**Range** thresholds best monitor high variance price feeds where the percent difference in price between sources is an unreliable indicator of a bad value. They are incompatibale, however, with non-numeric data feeds.

**Percentage** thresholds best monitor standard price feeds. The percentage is measured relative to the telliot value, not the reported value. In other words, if the telliot value is 1000, a 25% difference is 25% of 1000. Like range thresholds, percentage thresholds are incompatibable with non-numeric data feeds.

**Equality** thresholds best monitor data feeds where there is only one right answer. For example, `EVMCall` requests should be exactly equal to their expected telliot response. They aren't very useful for price feeds, though.

## Contributing:

- Install Python 3.9

Clone repo:
```bash
git clone https://github.com/fetch-io/disputable-values-monitor.git
```
Change directory:
```bash
cd disputable-values-monitor
```
Install dependencies with [Poetry](https://github.com/python-poetry/poetry):

```
./install.sh
source venv/bin/activate
```


Run tests:

Before executing `pytest`, initialize a `ganache-cli` in a separated terminal.
```sh
ganache-cli
```

```
pytest
```
Format/lint code:
```
pre-commit run --all-files
```
Check type hinting:
```
mypy --strict src --implicit-reexport --ignore-missing-imports --disable-error-code misc
```
Generate requirements.txt in case you have installed new dependencies:
```
poetry export -f requirements.txt --output requirements.txt --without-hashes
```

### Publishing a release
1. Ensure all tests are passing on `main` branch.
2. Remove "dev" from version in the `pyproject.toml` file. Example: version = "0.0.5dev" --> version = "0.0.5".
3. On github, go to "Releases" -> "Draft a new release" -> "Choose a tag".
4. Write in a new tag that corresponds with the version in `pyproject.toml` file. Example: v0.0.5
5. If the tag is v.0.0.5, the release title should be Release 0.0.5.
6. Click Auto-generate release notes.
7. Check the box for This is a pre-release.
8. Click Publish release.
9. Navigate to the Actions tab from the main page of the package on github and make sure the release workflow completes successfully.
10. Check to make sure the new version was released to test PyPI [here](https://test.pypi.org/project/fetch-disputables/).
11. Test downloading and using the new version of the package from test PyPI ([example](https://stackoverflow.com/questions/34514703/pip-install-from-pypi-works-but-from-testpypi-fails-cannot-find-requirements)).
12. Navigate back to the pre-release you just made and click edit (the pencil icon).
13. Uncheck the This is a pre-release box.
14. Publish the release.
15. Make sure the release github action goes through.
16. Download and test the new release on PyPI official [here](https://pypi.org/project/fetch-disputables/).
17. Change the package version in **pyproject.toml** to be the next development version. For example, if you just released version 0.0.5, change **version** to be "0.0.6dev0".
