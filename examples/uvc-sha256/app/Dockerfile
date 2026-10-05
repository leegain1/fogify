# One image for both roles:
#   edge server node : command: ["uvc-server"]        (default)
#   local node       : command: ["uvc-client", "idle"] then `docker exec ... uvc-client run ...`
FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod ./
COPY internal ./internal
COPY cmd ./cmd
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/uvc-server ./cmd/uvc-server \
 && CGO_ENABLED=0 GOOS=linux go build -o /out/uvc-client ./cmd/uvc-client

# alpine instead of upstream's scratch: Fogify's command action and debugging
# (ping, wget) need a shell.
FROM alpine:3.20

# Fogify's stress action runs `cpulimit --limit L -i -- stress --cpu N --timeout T`
# inside the container (FogifyModel/actions.py). stress-ng accepts the same flags.
RUN apk add --no-cache cpulimit stress-ng \
 && ln -s /usr/bin/stress-ng /usr/local/bin/stress \
 && mkdir -p /fogify

COPY --from=builder /out/ /usr/local/bin/

EXPOSE 8080
CMD ["uvc-server"]
