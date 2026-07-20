FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o /ingestor .

FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /ingestor /ingestor
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --retries=6 CMD ["/ingestor", "healthcheck"]
ENTRYPOINT ["/ingestor"]
