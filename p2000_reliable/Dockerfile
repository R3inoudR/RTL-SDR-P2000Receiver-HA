FROM debian:bookworm-slim

ENV LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        ca-certificates \
        multimon-ng \
        python3 \
        python3-geopy \
        python3-paho-mqtt \
        python3-requests \
        python3-usb \
        rtl-sdr \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY p2000.py reliable.py p2000.sqlite3 /
COPY sdl_ids.txt /var/lib/sdl_ids.txt

ARG BUILD_VERSION=1.1.0
ARG BUILD_ARCH=amd64
LABEL io.hass.name="P2000 RTL-SDR Reliable" \
    io.hass.description="P2000 reception with conservative location verification and strict radius filtering" \
    io.hass.type="app" \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.arch="${BUILD_ARCH}" \
    org.opencontainers.image.source="https://github.com/R3inoudR/RTL-SDR-P2000Receiver-HA" \
    org.opencontainers.image.licenses="MIT"

ENTRYPOINT ["python3", "/p2000.py"]
