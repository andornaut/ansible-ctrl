# The image `make test` runs tests/lint.sh in. Every tool the checks call is baked in at the
# version the checkout pins, so a run needs no network: rebuilt only when one of the files
# copied below changes. The build context is those files alone (tests/container/test.sh
# streams them), so no other edit invalidates the cache.
FROM ubuntu:24.04@sha256:008173c23f95b170204355c12626cb5a965d779a7e1283b09e9cffbb1bf33ca3

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl git make python3 python3-venv xz-utils \
    && rm -rf /var/lib/apt/lists/*

# .nvmrc's version, checked against the release's published SHA-256.
ARG NODE_VERSION=24.21.0
ARG TARGETARCH
RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
        amd64) arch=x64 sum=fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6 ;; \
        arm64) arch=arm64 sum=6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2 ;; \
        *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    tarball="node-v${NODE_VERSION}-linux-${arch}.tar.xz"; \
    curl -fsSLo "/tmp/${tarball}" "https://nodejs.org/dist/v${NODE_VERSION}/${tarball}"; \
    echo "${sum}  /tmp/${tarball}" | sha256sum -c -; \
    tar -xJf "/tmp/${tarball}" -C /usr/local --strip-components=1 --no-same-owner; \
    rm "/tmp/${tarball}"

# A non-root account owning nothing on the host, which is the uid the checks run as.
RUN useradd --uid 10001 --user-group --create-home lint \
    && install -d -o lint -g lint /work /opt/lint-venv /opt/collections /opt/npm
USER lint

# tests/lint.sh's own venv layout: a copy of requirements-dev.txt beside the tools is the
# stamp that tells it the venv is current, so it never reaches for pip.
COPY --chown=lint:lint requirements-dev.txt /opt/lint-venv/requirements-dev.txt
RUN python3 -m venv /opt/lint-venv \
    && /opt/lint-venv/bin/pip install --no-cache-dir --quiet -r /opt/lint-venv/requirements-dev.txt

# requirements.yml pins no versions, so these are whatever was current when this layer
# was built; `docker builder prune` or an edit to requirements.yml refreshes them.
COPY --chown=lint:lint requirements.yml /opt/collections/requirements.yml
RUN /opt/lint-venv/bin/ansible-galaxy collection install -r /opt/collections/requirements.yml -p /opt/collections

# --ignore-scripts: `prepare` installs git hooks, and there is no repository here.
COPY --chown=lint:lint package.json package-lock.json /opt/npm/
RUN cd /opt/npm && npm ci --ignore-scripts --no-audit --no-fund --silent

ENV PATH=/opt/lint-venv/bin:${PATH}
WORKDIR /work
