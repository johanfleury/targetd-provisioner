#
# Build image
#

FROM debian:buster as build

COPY . /src

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get -qq update \
    && apt-get -qq -y install --no-install-suggests --no-install-recommends \
      python3 \
      python3-venv \
    && python3 -m venv /venv/ \
    && /venv/bin/pip install --upgrade pip \
    && /venv/bin/pip install --upgrade /src

#
# Actual image
#

FROM gcr.io/distroless/python3-debian10

ARG BUILD_DATE
ARG VERSION
ARG REVISION

LABEL org.opencontainers.image.url="https://gitlab.com/Arcaik/targetd-provisioner"
LABEL source="https://gitlab.com/Arcaik/targetd-provisioner"
LABEL version=
LABEL revision=${REVISION}

LABEL org.opencontainers.image.title="targetd-provisioner"
LABEL org.opencontainers.image.description="targetd-provisioner is storage provisoner for Kubernetes that uses targetd as a backend."
LABEL org.opencontainers.image.authors="Johan Fleury <jfleury@arcaik.net>"
LABEL org.opencontainers.image.licenses="GPL-3.0-or-later"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.revision="${REVISION}"
LABEL org.opencontainers.image.url="https://gitlab.com/Arcaik/targetd-provisioner"
LABEL org.opencontainers.image.source="https://gitlab.com/Arcaik/targetd-provisioner"
LABEL org.opencontainers.image.created="${BUILD_DATE}"

COPY --from=build /venv/ /venv/

EXPOSE 8080
ENTRYPOINT ["/venv/bin/targetd-provisioner"]
