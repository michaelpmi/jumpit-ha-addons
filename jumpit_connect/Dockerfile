ARG BUILD_FROM
FROM ${BUILD_FROM}

# wg (ohne wg-quick), ip, nginx (TLS-Terminierung), lego (ACME DNS-01), curl/jq
RUN apk add --no-cache \
        wireguard-tools-wg \
        iproute2 \
        nginx \
        lego \
        curl \
        jq \
        openssl \
        python3 \
        py3-websockets

COPY rootfs/ /
RUN chmod a+x /run.sh

CMD ["/run.sh"]
