FROM python:3

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG VERSION
ENV VERSION ${VERSION:-master}

# install google chrome
RUN wget -q -O - "https://dl-ssl.google.com/linux/linux_signing_key.pub" | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
# hadolint ignore=DL3008
RUN apt-get -y update \
    && apt-get install -y google-chrome-stable unzip --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# install chromedriver
RUN wget -q -O /tmp/chromedriver.zip "http://chromedriver.storage.googleapis.com/$(\
    wget -q -O - https://chromedriver.storage.googleapis.com/LATEST_RELEASE \
    )/chromedriver_linux64.zip"
RUN unzip /tmp/chromedriver.zip chromedriver -d /usr/local/bin/

# set display port to avoid crash
ENV DISPLAY=:99

# pip
RUN python -m pip --no-cache-dir install git+https://github.com/eggplants/dojinvoice_db@${VERSION}

CMD ["dvdb"]
