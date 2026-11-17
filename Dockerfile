# Synapse (Matrix homeserver) for Railway.
# Upstream image pinned by version and digest; bump both together and add a CHANGELOG entry.
FROM ghcr.io/element-hq/synapse:v1.165.0@sha256:673b4223c81a7634fd07d832b939a58f97081cfdaae7cdd2d1664cdcf7611b62

COPY railway-start.py /railway-start.py
COPY log.config /conf/railway-log.config

ENV SYNAPSE_DATA_DIR=/data \
    PORT=8008

EXPOSE 8008
VOLUME ["/data"]

HEALTHCHECK --start-period=60s --interval=15s --timeout=5s \
    CMD curl -fSs "http://localhost:${PORT:-8008}/health" || exit 1

ENTRYPOINT ["python", "/railway-start.py"]
