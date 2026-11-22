# JiuwenSwarm image for a home NAS (UGREEN UGOS Pro, or any Docker host).
#
# Default build: installs the RELEASED jiuwenswarm from PyPI (no gitcode.com
# access needed, no web UI compile) and adds the fullstack-devco-swarm skill from
# this repository. To build from this repository's source instead, set
# DEVCO_DOCKERFILE=Dockerfile.source in .env.
ARG BASE_IMAGE=python:3.11.4-slim-bookworm
FROM ${BASE_IMAGE}

# git: every DevCo role commits its work. nodejs/npm: lets the swarm build and
# test JavaScript frontends inside /projects.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git nodejs npm \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 --shell /bin/bash app && mkdir -p /app /projects \
    && chown app:app /app /projects
USER app
ENV PATH=$PATH:/home/app/.local/bin

# PIP_INDEX_URL: default pypi.org, or a nearer mirror, e.g.
#   --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG JIUWENSWARM_VERSION=0.2.4b3.post2
RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" "jiuwenswarm==${JIUWENSWARM_VERSION}"

RUN git config --global user.name "DevCo Swarm" \
    && git config --global user.email "devco@localhost" \
    && git config --global init.defaultBranch main

# The DevCo skill is not in the PyPI release yet; the entrypoint installs it into
# ~/.jiuwenswarm/agent/workspace/skills on first boot.
COPY --chown=app:app jiuwenswarm/resources/agent/workspace/skills/fullstack-devco-swarm \
     /app/skills/fullstack-devco-swarm
COPY --chown=app:app deploy/ugreen-nas/entrypoint.sh /app/entrypoint.sh
ENTRYPOINT ["/bin/bash", "/app/entrypoint.sh"]
