// Package producer wraps a Kafka writer for raw_articles events.
package producer

import (
	"context"
	"encoding/json"

	"github.com/segmentio/kafka-go"

	"pulse/ingestor/internal/event"
)

// Producer publishes Article events to a Kafka topic.
type Producer struct {
	writer *kafka.Writer
}

// New builds a Producer. Messages are keyed by source_id (via Hash balancer) so
// all events from one source item land on the same partition, preserving order.
func New(brokers []string, topic string) *Producer {
	return &Producer{
		writer: &kafka.Writer{
			Addr:         kafka.TCP(brokers...),
			Topic:        topic,
			Balancer:     &kafka.Hash{},
			RequiredAcks: kafka.RequireAll,
			Async:        false,
		},
	}
}

// Publish marshals and writes a single Article.
func (p *Producer) Publish(ctx context.Context, a event.Article) error {
	payload, err := json.Marshal(a)
	if err != nil {
		return err
	}
	return p.writer.WriteMessages(ctx, kafka.Message{
		Key:   []byte(a.SourceID),
		Value: payload,
	})
}

// Close flushes and releases the underlying writer.
func (p *Producer) Close() error {
	return p.writer.Close()
}
