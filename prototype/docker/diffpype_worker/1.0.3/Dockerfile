FROM ghcr.io/davecoulter/diffpype:1.0.2
LABEL description="Base Image for DiffPype 1.0.3"
LABEL maintainer="Dave Coulter (dcoulter@stsci.edu)"

SHELL ["/bin/bash", "-c"]

ENV CRDS_SERVER_URL="https://jwst-crds.stsci.edu"

# Install Python Dependencies
WORKDIR /app
COPY ./requirements.txt /app/requirements_5.txt

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements_5.txt

RUN rm -rf /var/lib/apt/lists/*