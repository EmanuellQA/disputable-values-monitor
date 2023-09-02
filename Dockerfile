FROM python:3.9.17-slim-bullseye

#install dependencies for build pip packages
RUN apt-get update && apt-get install -y protobuf-compiler gcc libc-dev linux-headers-generic expect

#install jinja2
RUN pip3 install --no-cache-dir Jinja2==3.1.2

#copy telliot core and change_address script
WORKDIR /usr/src/app/telliot-core
COPY ./telliot-core .
RUN pip install -e .
COPY ./change_address.py .

#copy telliot feeds
WORKDIR /usr/src/app/telliot-feeds
COPY ./telliot-feeds .
RUN pip install -e .

#copy dvm
WORKDIR /usr/src/app/disputable-values-monitor
COPY ./disputable-values-monitor .
ENV PYTHONPATH=${PYTHONPATH}:${PWD}

COPY ./podinit.sh .