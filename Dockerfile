FROM python:2.7-alpine

LABEL MAINTAINER Daniel Pryor <dpryor@pryorda.net>
LABEL NAME vmware_exporter
LABEL VERSION 0.20

WORKDIR /opt/vmware_exporter/

COPY . /opt/vmware_exporter/

RUN set -x; buildDeps="gcc python-dev musl-dev libffi-dev openssl openssl-dev" \
 && apk add --no-cache --update $buildDeps \
 && pip install -r requirements.txt \
 && apk del $buildDeps

EXPOSE 9272

CMD ["/opt/vmware_exporter/vmware_exporter/vmware_exporter.py"]
