# --- Build Stage ---
FROM golang:1.22-alpine AS builder

WORKDIR /app

COPY go.mod go.sum* ./
# RUN go mod download

COPY main.go ./

RUN CGO_ENABLED=0 GOOS=linux go build -v -o /app/main .

# --- OPS Extraction Stage ---
# Use a minimal image WITH a shell for OPS extraction
FROM alpine AS exportable

# Optionally, install ca-certificates if your app needs HTTPS
RUN apk add --no-cache ca-certificates

COPY --from=builder /app/main /main

CMD ["/main"]

# --- Final Deployment Stage ---
FROM scratch

COPY --from=builder /app/main /main

CMD ["/main"]
