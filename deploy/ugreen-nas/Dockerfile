# JiuwenSwarm image for a home NAS (UGREEN UGOS Pro, or any Docker host).
# Built from this repository checkout; see README.md in this folder.
ARG BASE_IMAGE=python:3.11.4-slim-bookworm
FROM ${BASE_IMAGE}

# git: the openjiuwen dependency is installed from git, and every DevCo role commits.
# nodejs/npm: builds the web UI and lets the swarm build/test JS frontends.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 --shell /bin/bash app && mkdir -p /app /projects \
    && chown app:app /app /projects
COPY --chown=app:app . /app/jiuwenswarm/
USER app
ENV PATH=$PATH:/home/app/.local/bin

WORKDIR /app/jiuwenswarm/jiuwenswarm/channels/web/frontend
RUN npm install && npm run build

# PIP_INDEX_URL: leave the default (pypi.org) or set a nearer mirror at build time,
# e.g. --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
WORKDIR /app/jiuwenswarm
RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" . ./packages/jiuwenswarm-tui

# Commits made by the agents need an identity; override in config if you like.
RUN git config --global user.name "DevCo Swarm" \
    && git config --global user.email "devco@localhost" \
    && git config --global init.defaultBranch main

COPY --chown=app:app deploy/ugreen-nas/entrypoint.sh /app/entrypoint.sh
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
