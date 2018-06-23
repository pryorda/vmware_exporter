FROM python:2.7-alpine

LABEL MAINTAINER  Daniel Pryor <dpryor@pryorda.net>

WORKDIR /opt/vmware_exporter/

COPY . /opt/vmware_exporter/
 
RUN set -x; buildDeps="gcc python-dev musl-dev libffi-dev openssl openssl-dev" \
 && apk add --no-cache --update $buildDeps \
 && pip install -r requirements.txt \
 && apk del $buildDeps

EXPOSE 9272

ENTRYPOINT ["/opt/vmware_exporter/vmware_exporter/vmware_exporter.py", "-c", "/opt/vmware_exporter/config.yml"]
