FROM ghcr.io/davecoulter/diffpype:1.0.0
LABEL description="Base Image for DiffPype 1.0.1"
LABEL maintainer="Dave Coulter (dcoulter@stsci.edu)"

SHELL ["/bin/bash", "-c"]

RUN apt-get -y update && apt-get -y upgrade
RUN apt-get -y install source-extractor

# Install SExtractpr
WORKDIR /sextractor
RUN git clone https://github.com/megalut/sewpy.git

WORKDIR /sextractor/sewpy
RUN python setup.py install

# Install Python Dependencies
WORKDIR /app
COPY ./requirements.txt /app/requirements_3.txt

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements_3.txt

RUN rm -rf /var/lib/apt/lists/*