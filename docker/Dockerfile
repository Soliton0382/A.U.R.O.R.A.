# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 A.U.R.O.R.A. Project
#
# Aurora with a cloud reasoner, for a machine without a GPU (owner, 2026-10-09). The encoder and re-ranker run on the
# CPU (torch's CPU build: no CUDA in the image); everything Aurora writes lives in the /data volume. Built from the
# repository's root:  docker compose -f docker/compose.yaml build   (guide: docs/DOCKER.md)
FROM caddy:2 AS caddy

FROM python:3.14-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg poppler-utils curl ca-certificates \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY --from=caddy /usr/bin/caddy /usr/bin/caddy
WORKDIR /opt/aurora
COPY requirements.txt .
# torch for the CPU first (PyPI's Linux wheel carries CUDA, gigabytes more), then the rest at requirements.txt's versions
RUN python -m venv .venv \
    && .venv/bin/pip install --no-cache-dir --upgrade pip \
    && .venv/bin/pip install --no-cache-dir torch==2.14.0 torchvision==0.29.0 --index-url https://download.pytorch.org/whl/cpu \
    && .venv/bin/pip install --no-cache-dir -r requirements.txt
COPY . .
# the code's fingerprint: a new image is signed again at its first start (the owner pulled it: the update)
RUN find sys/core sys/plugins install.sh -type f -not -path '*/__pycache__/*' | sort | xargs sha256sum | sha256sum \
      | cut -c1-16 > docker/BUILD \
    && install -m 755 docker/systemctl /usr/local/bin/systemctl \
    && chmod 755 docker/entrypoint.py
ENV AURORA_ENV_FILE=/data/.env AURORA_DOCKER=1 PYTHONUNBUFFERED=1 PATH=/opt/aurora/.venv/bin:$PATH
VOLUME /data
HEALTHCHECK --interval=60s --timeout=10s --start-period=600s CMD curl -fs http://127.0.0.1:9700/health || exit 1
ENTRYPOINT ["/opt/aurora/docker/entrypoint.py"]
