FROM ghcr.io/davecoulter/diffpype:1.0.1
LABEL description="Base Image for DiffPype 1.0.2"
LABEL maintainer="Dave Coulter (dcoulter@stsci.edu)"

SHELL ["/bin/bash", "-c"]

# Install Python Dependencies
WORKDIR /app
COPY ./requirements.txt /app/requirements_4.txt

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements_4.txt

RUN rm -rf /var/lib/apt/lists/*