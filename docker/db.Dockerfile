FROM postgres:16

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-server-dev-16 \
    libreadline-dev \
    libzstd-dev \
    liblz4-dev \
    zlib1g-dev \
    libssl-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG Q3C_VERSION=2.0.1
RUN curl -fsSL "https://github.com/segasai/q3c/archive/refs/tags/v${Q3C_VERSION}.tar.gz" \
    | tar -xz \
    && cd "q3c-${Q3C_VERSION}" \
    && make \
    && make install \
    && cd .. \
    && rm -rf "q3c-${Q3C_VERSION}"

COPY docker/db_init/ /docker-entrypoint-initdb.d/
