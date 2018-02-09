FROM python:2-slim

WORKDIR /usr/src/app

RUN buildDeps="gcc python-dev" \
 && apt-get update \
 && apt-get install -y --no-install-recommends $buildDeps \
 && pip install --no-cache-dir vmware_exporter \
 && SUDO_FORCE_REMOVE=yes \
 && apt-get purge -y --auto-remove \
                  -o APT::AutoRemove::RecommendsImportant=false \
                  $buildDeps \
 && rm -rf /var/lib/apt/lists/*

EXPOSE 9272

ENTRYPOINT ["vmware_exporter"]