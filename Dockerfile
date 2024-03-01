# Use the official Python 3.10 image as the base image
FROM python:3.9

RUN apt-get update && \
    apt-get install -y vim
    # Set the working directory inside the container
WORKDIR /app

# Copy the contents of the local "app" directory to the container's working directory
COPY . .
# Set the environment variable within the Dockerfile

# Run the install.sh script inside the container

ARG TELLIOT_BRANCH
ENV TELLIOT_BRANCH=$TELLIOT_BRANCH
RUN git submodule update --init --recursive
RUN echo $TELLIOT_BRANCH > my_branch.txt
RUN cd telliot-feeds && git checkout $TELLIOT_BRANCH
RUN cd telliot-feeds/telliot-core && git checkout $TELLIOT_BRANCH

RUN pip install .
RUN pip install -r requirements.txt
CMD ["python", "initialize_dvm_docker.py"]
#RUN python -c "import telliot_core; print(f'telliot-core version installed - {telliot_core.__version__}')"
#RUN python -c "import telliot_feeds; print(f'telliot-feeds version installed - {telliot_feeds.__version__}')"
#RUN /usr/local/lib/python3.10/site-packages/telliot_core/data/contract_directory.dev.json /usr/local/lib/python3.10/site-packages/telliot_core/data/contract_directory.json

# Specify the command to run when the container starts
#CMD [ "bash", "runtime.sh" ] #Uncomment this line if you want to test locally