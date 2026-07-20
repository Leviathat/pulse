package main

import (
	"context"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus/promhttp"

	"pulse/ingestor/internal/hn"
	"pulse/ingestor/internal/poller"
	"pulse/ingestor/internal/producer"
)

func main() {
	// Used by the container HEALTHCHECK: distroless has no shell/curl,
	// so the binary probes itself.
	if len(os.Args) > 1 && os.Args[1] == "healthcheck" {
		resp, err := http.Get("http://localhost:8080/healthz")
		if err != nil || resp.StatusCode != http.StatusOK {
			os.Exit(1)
		}
		return
	}

	brokers := strings.Split(getenv("KAFKA_BROKERS", "kafka:9092"), ",")
	topic := getenv("KAFKA_TOPIC", "raw_articles")
	addr := getenv("HTTP_ADDR", ":8080")
	interval := getenvDuration("POLL_INTERVAL", 15*time.Second)
	maxPerPoll := getenvInt("MAX_ITEMS_PER_POLL", 60)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, os.Interrupt)
	defer stop()

	prod := producer.New(brokers, topic)
	defer func() { _ = prod.Close() }()

	pl := poller.New(poller.Config{Interval: interval, MaxPerPoll: maxPerPoll}, hn.NewClient(), prod)
	go pl.Run(ctx)

	srv := &http.Server{Addr: addr, Handler: router(brokers)}
	go func() {
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("http server failed", "error", err)
			os.Exit(1)
		}
	}()
	slog.Info("ingestor listening", "addr", addr, "kafka", brokers, "topic", topic, "interval", interval)

	<-ctx.Done()
	slog.Info("shutting down")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutdownCtx)
}

func router(brokers []string) http.Handler {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())

	r.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})
	r.GET("/readyz", func(c *gin.Context) {
		conn, err := net.DialTimeout("tcp", brokers[0], 2*time.Second)
		if err != nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"status": "kafka unreachable"})
			return
		}
		_ = conn.Close()
		c.JSON(http.StatusOK, gin.H{"status": "ready"})
	})
	r.GET("/metrics", gin.WrapH(promhttp.Handler()))
	return r
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getenvDuration(key string, fallback time.Duration) time.Duration {
	if v := os.Getenv(key); v != "" {
		if d, err := time.ParseDuration(v); err == nil {
			return d
		}
		slog.Warn("invalid duration, using fallback", "key", key, "value", v)
	}
	return fallback
}

func getenvInt(key string, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
		slog.Warn("invalid int, using fallback", "key", key, "value", v)
	}
	return fallback
}
