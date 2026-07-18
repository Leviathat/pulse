package main

import (
	"context"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
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

	brokers := getenv("KAFKA_BROKERS", "kafka:9092")
	addr := getenv("HTTP_ADDR", ":8080")

	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())

	r.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})
	r.GET("/readyz", func(c *gin.Context) {
		conn, err := net.DialTimeout("tcp", brokers, 2*time.Second)
		if err != nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"status": "kafka unreachable"})
			return
		}
		_ = conn.Close()
		c.JSON(http.StatusOK, gin.H{"status": "ready"})
	})
	r.GET("/metrics", func(c *gin.Context) {
		c.String(http.StatusOK, "# TODO: Prometheus metrics (stage 1)\n")
	})

	srv := &http.Server{Addr: addr, Handler: r}
	go func() {
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("http server failed", "error", err)
			os.Exit(1)
		}
	}()
	slog.Info("ingestor stub listening", "addr", addr, "kafka", brokers)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, os.Interrupt)
	defer stop()
	<-ctx.Done()

	slog.Info("shutting down")
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(shutdownCtx)
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
