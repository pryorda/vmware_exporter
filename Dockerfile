FROM python:3.12-alpine

LABEL org.opencontainers.image.authors="Daniel Pryor <daniel@pryorda.net>"
LABEL org.opencontainers.image.title="vmware_exporter"

WORKDIR /opt/vmware_exporter/
COPY . /opt/vmware_exporter/

# Alpine package versions disappear on every release, so they are not pinned here.
# hadolint ignore=DL3018
RUN set -x; buildDeps="gcc python3-dev musl-dev libffi-dev openssl openssl-dev rust cargo" \
 && apk add --no-cache --update $buildDeps \
 && pip install --no-cache-dir -r requirements.txt . \
 && apk del $buildDeps

EXPOSE 9272

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/usr/local/bin/vmware_exporter"]
