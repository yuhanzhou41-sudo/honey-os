FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HONEYOS_HOME=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY dist/ /tmp/dist/
RUN set -- /tmp/dist/honeyos-*.whl; \
    pip install "${1}[honeyos]" \
    && rm -rf /tmp/dist

COPY seed-home/ /seed-home/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
