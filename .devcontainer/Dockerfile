FROM mcr.microsoft.com/devcontainers/base:ubuntu

SHELL ["/bin/bash", "-o", "pipefail", "-c"]


RUN wget -q -O - "https://dl-ssl.google.com/linux/linux_signing_key.pub" | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'

# hadolint ignore=DL3008
RUN apt-get -y update \
    && apt-get install -y google-chrome-stable unzip --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
