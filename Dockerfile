FROM python:3.6-alpine as linter
# Runs required lints so automated builds are a little more fluid

WORKDIR /opt/vmware_exporter/
COPY . /opt/vmware_exporter/

RUN pip install flake8 && \
  apk add --no-cache --update nodejs npm && \
  npm install -g dockerfilelint

RUN flake8 vmware_exporter
RUN dockerfilelint Dockerfile

FROM python:3.6-alpine

LABEL MAINTAINER="Daniel Pryor <daniel@pryorda.net>"
LABEL NAME=vmware_exporter

WORKDIR /opt/vmware_exporter/

COPY . /opt/vmware_exporter/

RUN set -x; buildDeps="gcc python-dev musl-dev libffi-dev openssl openssl-dev" \
 && apk add --no-cache --update $buildDeps \
 && pip install -r requirements.txt . \
 && apk del $buildDeps

EXPOSE 9272

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/usr/local/bin/vmware_exporter"]
