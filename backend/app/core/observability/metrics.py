"""Enhanced metrics collector with histogram support.

Provides a general-purpose metrics collection system supporting:
- Counters: Monotonically increasing values
- Gauges: Point-in-time values that can go up or down
- Histograms: Distribution of values with percentile calculations
"""

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple


class MetricType(Enum):
    """Types of metrics supported by the collector.

    COUNTER: Monotonically increasing value (e.g., request count)
    GAUGE: Point-in-time value that can increase or decrease (e.g., memory usage)
    HISTOGRAM: Distribution of values (e.g., request latency)
    """
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass
class HistogramBucket:
    """Histogram bucket for tracking value distributions.

    Tracks observations in fixed buckets for percentile calculation.
    Uses exponential bucket boundaries for efficient storage.
    """

    # Bucket boundaries (exclusive upper bounds)
    # Values: 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, +Inf
    BUCKETS: Tuple[float, ...] = field(default=(
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, float('inf')
    ))

    # Bucket counts (one more than BUCKETS for +Inf)
    _counts: List[int] = field(default_factory=list)
    # Raw observations for exact percentile calculation
    _observations: List[float] = field(default_factory=list)
    # Sum of all observations
    _sum: float = field(default=0.0)
    # Count of observations
    _count: int = field(default=0)
    # Lock for thread-safe updates
    _lock: Lock = field(default_factory=Lock)

    def __post_init__(self):
        """Initialize counts list based on bucket size."""
        if not self._counts:
            object.__setattr__(self, '_counts', [0] * (len(self.BUCKETS) + 1))

    def add(self, value: float) -> None:
        """Add an observation to the histogram.

        Args:
            value: The observed value to add
        """
        with self._lock:
            self._observations.append(value)
            self._sum += value
            self._count += 1

            # Find the appropriate bucket
            for i, boundary in enumerate(self.BUCKETS):
                if value <= boundary:
                    self._counts[i] += 1
                    break

    def percentile(self, p: float) -> float:
        """Calculate the percentile value.

        Args:
            p: Percentile to calculate (0.0 to 100.0)

        Returns:
            The value at the given percentile
        """
        with self._lock:
            if not self._observations:
                return 0.0

            if p <= 0:
                return min(self._observations)
            if p >= 100:
                return max(self._observations)

            # Sort observations for percentile calculation
            sorted_obs = sorted(self._observations)
            k = (len(sorted_obs) - 1) * (p / 100.0)
            f = int(k)
            c = f + 1

            if c >= len(sorted_obs):
                return sorted_obs[-1]

            return sorted_obs[f] + (k - f) * (sorted_obs[c] - sorted_obs[f])

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive histogram statistics.

        Returns:
            Dictionary with count, sum, min, max, avg, and percentiles
        """
        with self._lock:
            if not self._observations:
                return {
                    "count": 0,
                    "sum": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                    "avg": 0.0,
                    "p50": 0.0,
                    "p90": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                }

            sorted_obs = sorted(self._observations)
            n = len(sorted_obs)

            return {
                "count": self._count,
                "sum": self._sum,
                "min": sorted_obs[0],
                "max": sorted_obs[-1],
                "avg": self._sum / n,
                "p50": self.percentile(50),
                "p90": self.percentile(90),
                "p95": self.percentile(95),
                "p99": self.percentile(99),
            }

    def reset(self) -> None:
        """Reset all histogram data."""
        with self._lock:
            self._observations.clear()
            self._sum = 0.0
            self._count = 0
            self._counts = [0] * (len(self.BUCKETS) + 1)


class MetricsCollector:
    """Enhanced metrics collector with histogram support.

    Thread-safe metrics collection supporting counters, gauges, and histograms.
    Provides a unified API for recording and retrieving metrics.

    Metrics are stored with labels for dimensional querying:
    - counters: name -> labels -> value
    - gauges: name -> labels -> value
    - histograms: name -> labels -> HistogramBucket
    """

    def __init__(self) -> None:
        """Initialize the metrics collector."""
        self._counters: Dict[Tuple[str, tuple], float] = defaultdict(float)
        self._gauges: Dict[Tuple[str, tuple], float] = defaultdict(float)
        self._histograms: Dict[Tuple[str, tuple], HistogramBucket] = {}
        self._lock = Lock()

    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> Tuple[str, tuple]:
        """Create a hashable key from name and labels.

        Args:
            name: Metric name
            labels: Optional label dict

        Returns:
            Tuple of (name, sorted_label_items)
        """
        if labels:
            return (name, tuple(sorted(labels.items())))
        return (name, ())

    def record(
        self,
        metric_type: MetricType,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a metric value.

        Args:
            metric_type: Type of metric (COUNTER, GAUGE, HISTOGRAM)
            name: Metric name
            value: Metric value
            labels: Optional labels for dimensional metrics
        """
        key = self._make_key(name, labels)

        with self._lock:
            if metric_type == MetricType.COUNTER:
                self._counters[key] += value
            elif metric_type == MetricType.GAUGE:
                self._gauges[key] = value
            elif metric_type == MetricType.HISTOGRAM:
                if key not in self._histograms:
                    self._histograms[key] = HistogramBucket()
                self._histograms[key].add(value)

    def increment(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
        delta: float = 1.0,
    ) -> None:
        """Increment a counter metric.

        Args:
            name: Counter name
            labels: Optional labels
            delta: Amount to increment (default: 1.0)
        """
        self.record(MetricType.COUNTER, name, delta, labels)

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge metric value.

        Args:
            name: Gauge name
            value: Gauge value
            labels: Optional labels
        """
        self.record(MetricType.GAUGE, name, value, labels)

    def timing(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a timing value (in milliseconds) as a histogram.

        Args:
            name: Timing metric name
            value: Duration in milliseconds
            labels: Optional labels
        """
        self.record(MetricType.HISTOGRAM, name, value, labels)

    def get_counter(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> float:
        """Get the current value of a counter.

        Args:
            name: Counter name
            labels: Optional labels

        Returns:
            Current counter value (0.0 if not found)
        """
        key = self._make_key(name, labels)
        with self._lock:
            return self._counters.get(key, 0.0)

    def get_gauge(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> float:
        """Get the current value of a gauge.

        Args:
            name: Gauge name
            labels: Optional labels

        Returns:
            Current gauge value (0.0 if not found)
        """
        key = self._make_key(name, labels)
        with self._lock:
            return self._gauges.get(key, 0.0)

    def get_histogram_stats(
        self,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Get statistics for a histogram.

        Args:
            name: Histogram name
            labels: Optional labels

        Returns:
            Dictionary with histogram statistics or empty dict if not found
        """
        key = self._make_key(name, labels)
        with self._lock:
            histogram = self._histograms.get(key)
            if histogram:
                return histogram.get_stats()
            return {
                "count": 0,
                "sum": 0.0,
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
                "p50": 0.0,
                "p90": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            }

    async def get_statistics(self, prefix: str) -> Dict[str, Any]:
        """Get aggregated statistics for metrics matching a prefix.

        Args:
            prefix: Metric name prefix to filter by

        Returns:
            Dictionary with aggregated counters, gauges, and histograms
        """
        # Simulate async operation for compatibility with async codebases
        await asyncio.sleep(0)

        with self._lock:
            result: Dict[str, Any] = {
                "counters": {},
                "gauges": {},
                "histograms": {},
            }

            # Collect matching counters
            for (name, label_tuple), value in self._counters.items():
                if name.startswith(prefix):
                    labels = dict(label_tuple) if label_tuple else {}
                    key = f"{name}_{hash(str(labels))}" if labels else name
                    result["counters"][key] = {
                        "name": name,
                        "value": value,
                        "labels": labels,
                    }

            # Collect matching gauges
            for (name, label_tuple), value in self._gauges.items():
                if name.startswith(prefix):
                    labels = dict(label_tuple) if label_tuple else {}
                    key = f"{name}_{hash(str(labels))}" if labels else name
                    result["gauges"][key] = {
                        "name": name,
                        "value": value,
                        "labels": labels,
                    }

            # Collect matching histograms
            for (name, label_tuple), histogram in self._histograms.items():
                if name.startswith(prefix):
                    labels = dict(label_tuple) if label_tuple else {}
                    key = f"{name}_{hash(str(labels))}" if labels else name
                    result["histograms"][key] = {
                        "name": name,
                        "labels": labels,
                        **histogram.get_stats(),
                    }

            return result

    def reset(self) -> None:
        """Reset all metrics to initial state."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()


# Global singleton instance
_collector: Optional[MetricsCollector] = None
_collector_lock = Lock()


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector singleton.

    Returns:
        The global MetricsCollector instance
    """
    global _collector

    if _collector is None:
        with _collector_lock:
            # Double-check locking pattern
            if _collector is None:
                _collector = MetricsCollector()

    return _collector
