"""Tests for observability metrics collector."""

import pytest

from app.core.observability.metrics import (
    MetricType,
    HistogramBucket,
    MetricsCollector,
    get_metrics_collector,
)


class TestHistogramBucket:
    """Tests for HistogramBucket dataclass."""

    def test_add_single_value(self):
        """Test adding a single value to histogram."""
        bucket = HistogramBucket()
        bucket.add(1.5)
        stats = bucket.get_stats()

        assert stats["count"] == 1
        assert stats["sum"] == 1.5
        assert stats["min"] == 1.5
        assert stats["max"] == 1.5
        assert stats["avg"] == 1.5

    def test_add_multiple_values(self):
        """Test adding multiple values to histogram."""
        bucket = HistogramBucket()
        bucket.add(1.0)
        bucket.add(2.0)
        bucket.add(3.0)
        stats = bucket.get_stats()

        assert stats["count"] == 3
        assert stats["sum"] == 6.0
        assert stats["min"] == 1.0
        assert stats["max"] == 3.0
        assert stats["avg"] == 2.0

    def test_percentile_calculation(self):
        """Test percentile calculation."""
        bucket = HistogramBucket()
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        for v in values:
            bucket.add(v)

        assert bucket.percentile(0) == 1.0
        assert bucket.percentile(100) == 10.0
        assert bucket.percentile(50) == 5.5  # Median
        assert bucket.percentile(25) == 3.25  # Q1

    def test_percentile_empty(self):
        """Test percentile calculation with empty histogram."""
        bucket = HistogramBucket()
        assert bucket.percentile(50) == 0.0

    def test_percentile_single_value(self):
        """Test percentile calculation with single value."""
        bucket = HistogramBucket()
        bucket.add(5.0)

        assert bucket.percentile(0) == 5.0
        assert bucket.percentile(50) == 5.0
        assert bucket.percentile(100) == 5.0

    def test_get_stats_includes_percentiles(self):
        """Test that get_stats includes standard percentiles."""
        bucket = HistogramBucket()
        for v in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]:
            bucket.add(v)

        stats = bucket.get_stats()

        assert "p50" in stats
        assert "p90" in stats
        assert "p95" in stats
        assert "p99" in stats
        assert stats["p50"] == 5.5

    def test_reset(self):
        """Test resetting histogram."""
        bucket = HistogramBucket()
        bucket.add(1.0)
        bucket.add(2.0)
        bucket.reset()

        stats = bucket.get_stats()
        assert stats["count"] == 0
        assert stats["sum"] == 0.0


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    def test_metrics_collector_record_counter(self):
        """Test recording counter metric."""
        collector = MetricsCollector()
        collector.record(MetricType.COUNTER, "requests", 1.0)

        assert collector.get_counter("requests") == 1.0

    def test_metrics_collector_record_gauge(self):
        """Test recording gauge metric."""
        collector = MetricsCollector()
        collector.record(MetricType.GAUGE, "memory", 1024.0)

        assert collector.get_gauge("memory") == 1024.0

    def test_metrics_collector_record_histogram(self):
        """Test recording histogram metric."""
        collector = MetricsCollector()
        collector.record(MetricType.HISTOGRAM, "latency", 100.0)

        stats = collector.get_histogram_stats("latency")
        assert stats["count"] == 1
        assert stats["sum"] == 100.0

    def test_metrics_collector_histogram(self):
        """Test histogram with multiple observations."""
        collector = MetricsCollector()

        # Record multiple latency values
        latencies = [50.0, 100.0, 150.0, 200.0, 250.0]
        for latency in latencies:
            collector.timing("api_latency", latency)

        stats = collector.get_histogram_stats("api_latency")

        assert stats["count"] == 5
        assert stats["min"] == 50.0
        assert stats["max"] == 250.0
        assert stats["avg"] == 150.0

    def test_metrics_collector_increment(self):
        """Test incrementing counter."""
        collector = MetricsCollector()

        collector.increment("page_views")
        assert collector.get_counter("page_views") == 1.0

        collector.increment("page_views", delta=5.0)
        assert collector.get_counter("page_views") == 6.0

    def test_metrics_collector_set_gauge(self):
        """Test setting gauge value."""
        collector = MetricsCollector()

        collector.set_gauge("temperature", 20.5)
        assert collector.get_gauge("temperature") == 20.5

        collector.set_gauge("temperature", 21.0)
        assert collector.get_gauge("temperature") == 21.0  # Overwrites, doesn't accumulate

    def test_metrics_collector_timing(self):
        """Test recording timing values."""
        collector = MetricsCollector()

        collector.timing("db_query", 25.5)
        collector.timing("db_query", 30.0)

        stats = collector.get_histogram_stats("db_query")
        assert stats["count"] == 2
        assert stats["sum"] == 55.5

    def test_metrics_collector_with_labels(self):
        """Test metrics with dimensional labels."""
        collector = MetricsCollector()

        collector.increment("requests", labels={"endpoint": "/api/users"})
        collector.increment("requests", labels={"endpoint": "/api/posts"})

        assert collector.get_counter("requests", labels={"endpoint": "/api/users"}) == 1.0
        assert collector.get_counter("requests", labels={"endpoint": "/api/posts"}) == 1.0

        # Gauge with labels
        collector.set_gauge("memory", 1024.0, labels={"host": "server1"})
        collector.set_gauge("memory", 2048.0, labels={"host": "server2"})

        assert collector.get_gauge("memory", labels={"host": "server1"}) == 1024.0
        assert collector.get_gauge("memory", labels={"host": "server2"}) == 2048.0

    def test_metrics_collector_histogram_with_labels(self):
        """Test histogram with labels."""
        collector = MetricsCollector()

        collector.timing("latency", 100.0, labels={"endpoint": "/api/users"})
        collector.timing("latency", 200.0, labels={"endpoint": "/api/posts"})

        stats_users = collector.get_histogram_stats("latency", labels={"endpoint": "/api/users"})
        stats_posts = collector.get_histogram_stats("latency", labels={"endpoint": "/api/posts"})

        assert stats_users["count"] == 1
        assert stats_users["sum"] == 100.0
        assert stats_posts["count"] == 1
        assert stats_posts["sum"] == 200.0

    def test_metrics_collector_get_nonexistent(self):
        """Test getting non-existent metrics returns defaults."""
        collector = MetricsCollector()

        assert collector.get_counter("nonexistent") == 0.0
        assert collector.get_gauge("nonexistent") == 0.0

        stats = collector.get_histogram_stats("nonexistent")
        assert stats["count"] == 0

    def test_metrics_collector_get_statistics(self):
        """Test get_statistics with prefix filtering."""
        collector = MetricsCollector()

        # Add metrics with different prefixes
        collector.increment("api_requests_total")
        collector.increment("api_requests_total")
        collector.set_gauge("api_memory_usage", 1024.0)
        collector.timing("api_latency_ms", 100.0)

        collector.increment("db_queries_total")
        collector.set_gauge("db_connections", 5.0)

        # Get stats for "api" prefix
        import asyncio

        stats = asyncio.run(collector.get_statistics("api"))

        assert len(stats["counters"]) == 1
        assert "api_requests_total" in stats["counters"]["api_requests_total"]["name"]
        assert stats["counters"]["api_requests_total"]["value"] == 2.0

        assert len(stats["gauges"]) == 1
        assert stats["gauges"]["api_memory_usage"]["value"] == 1024.0

        assert len(stats["histograms"]) == 1
        assert stats["histograms"]["api_latency_ms"]["count"] == 1

    def test_metrics_collector_reset(self):
        """Test resetting all metrics."""
        collector = MetricsCollector()

        collector.increment("counter1")
        collector.set_gauge("gauge1", 100.0)
        collector.timing("histogram1", 50.0)

        collector.reset()

        assert collector.get_counter("counter1") == 0.0
        assert collector.get_gauge("gauge1") == 0.0

        stats = collector.get_histogram_stats("histogram1")
        assert stats["count"] == 0

    def test_metrics_collector_counter_accumulates(self):
        """Test that counters accumulate across multiple records."""
        collector = MetricsCollector()

        collector.record(MetricType.COUNTER, "total", 5.0)
        collector.record(MetricType.COUNTER, "total", 3.0)

        assert collector.get_counter("total") == 8.0


class TestGlobalMetricsCollector:
    """Tests for global metrics collector factory."""

    def test_get_metrics_collector_singleton(self):
        """Test that get_metrics_collector returns singleton."""
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()

        assert collector1 is collector2

    def test_global_collector_persists_state(self):
        """Test that global collector persists state across calls."""
        collector = get_metrics_collector()
        collector.increment("test_metric", delta=10.0)

        # Get the collector again
        collector2 = get_metrics_collector()
        assert collector2.get_counter("test_metric") == 10.0

    def test_global_collector_independent_instances(self):
        """Test that direct MetricsCollector instances are independent."""
        collector1 = MetricsCollector()
        collector2 = MetricsCollector()

        collector1.increment("test")
        collector2.increment("test")

        assert collector1.get_counter("test") == 1.0
        assert collector2.get_counter("test") == 1.0  # Separate instance
