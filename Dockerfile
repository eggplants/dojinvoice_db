FROM python:3

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG VERSION
ENV VERSION ${VERSION:-main}

# set display port to avoid crash
ENV DISPLAY=:99

# pip
RUN python -m pip --no-cache-dir install git+https://github.com/eggplants/dojinvoice_db@${VERSION}

CMD ["dvdb"]
