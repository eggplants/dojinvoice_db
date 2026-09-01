FROM python:3.14-slim@sha256:656d12e70054d5fda18a045e2494c96701e9792dd1445f95b3d038df954f57e9 AS builder

ARG VERSION
ENV VERSION=${VERSION:-master}

RUN pip install --upgrade pip
RUN apt update && apt install -y git
RUN ln -s /usr/local/bin/python3 /usr/bin/python3
RUN /usr/bin/python3 -m venv /opt/venv
RUN /opt/venv/bin/pip install git+https://github.com/eggplants/dojinvoice_db@${VERSION}

FROM al3xos/python-distroless:3.14.4-debian13@sha256:07c0e292fb9675075be9fe450b950c2f54e13d4f20f497aa7456af969788975f
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH="/opt/venv/lib/python3.14/site-packages"

ENTRYPOINT ["python", "/opt/venv/bin/dvdb"]
