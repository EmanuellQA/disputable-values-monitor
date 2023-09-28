#!/bin/bash

git submodule update --init --recursive
git submodule update --remote --recursive

python -m venv venv

source venv/bin/activate

pip install .
pip install -r requirements.txt

python -c "import telliot_core; print(f'telliot-core version installed - {telliot_core.__version__}')"
python -c "import telliot_feeds; print(f'telliot-feeds version installed - {telliot_feeds.__version__}')"