// Package metrics holds the Prometheus collectors exposed on /metrics.
package metrics

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// ArticlesProduced counts events successfully written to Kafka, by source.
	ArticlesProduced = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "pulse_ingestor_articles_produced_total",
		Help: "Articles normalized and produced to Kafka, by source.",
	}, []string{"source"})

	// ItemsSkipped counts fetched items dropped during normalization.
	ItemsSkipped = promauto.NewCounter(prometheus.CounterOpts{
		Name: "pulse_ingestor_items_skipped_total",
		Help: "Fetched items dropped as deleted/dead/non-story.",
	})

	// SourceErrors counts failures talking to a source or to Kafka.
	SourceErrors = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "pulse_ingestor_source_errors_total",
		Help: "Errors while fetching from a source or producing, by kind.",
	}, []string{"source", "kind"})

	// LastPollUnix is the wall-clock time of the last completed poll cycle.
	// Scrapers derive poll lag as (now - this).
	LastPollUnix = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "pulse_ingestor_last_poll_timestamp_seconds",
		Help: "Unix timestamp of the last completed poll cycle.",
	})
)
