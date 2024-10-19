#
# Builder image
#

FROM golang:1.23 as builder

WORKDIR /go/src
COPY . .

ENV CGO_ENABLED=0

RUN go get github.com/mdomke/git-semver/v6 \
    && go mod tidy \
    && go build -v \
      -ldflags "\
        -X main.Version=$(git semver --no-pre) \
        -X main.Revision=$(git semver) \
        -X main.Branch=$(git branch --show-current) \
        -X main.BuildUser=$(id -u --name)@$(hostname) \
        -X main.BuildDate=$(date --utc --iso-8601=seconds)" \
      -o /go/bin/targetd-provisioner \
      cmd/main.go

#
# Actual image
#

FROM gcr.io/distroless/static:latest

LABEL org.opencontainers.image.title="targetd-provisioner"
LABEL org.opencontainers.image.description="targetd-provisioner is storage provisoner for Kubernetes that uses targetd as a backend."
LABEL org.opencontainers.image.authors="Johan Fleury <jfleury@arcaik.net>"
LABEL org.opencontainers.image.licenses="GPL-3.0-or-later"
LABEL org.opencontainers.image.url="https://gitlab.com/Arcaik/targetd-provisioner"
LABEL org.opencontainers.image.source="https://gitlab.com/Arcaik/targetd-provisioner"

COPY --from=builder /go/bin/targetd-provisioner /targetd-provisioner

ENTRYPOINT ["/targetd-provisioner"]
