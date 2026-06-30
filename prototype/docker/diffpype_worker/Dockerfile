FROM python:3.10-bullseye
LABEL description="Base Image for DiffPype 1.0.0"
LABEL maintainer="Dave Coulter (dcoulter@stsci.edu)"

SHELL ["/bin/bash", "-c"]

# Install HOTPANTS
WORKDIR /hotpants
COPY ./hotpants_arm64_linux /hotpants

RUN apt-get -y update && apt-get -y upgrade
RUN apt-get -y install libcfitsio-dev wcslib-dev nano default-libmysqlclient-dev

RUN make

# Install Python Dependencies
WORKDIR /app
COPY ./requirements_1.txt /app/requirements_1.txt
COPY ./requirements_2.txt /app/requirements_2.txt

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements_1.txt
RUN pip install --no-cache-dir -r requirements_2.txt

# Create I/O Dirs
RUN mkdir -p /diffpype_io

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/hotpants:$PATH"

RUN rm -rf /var/lib/apt/lists/*