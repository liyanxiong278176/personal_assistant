# Redis Cache Layer

Provides cross-instance session state sharing with circuit breaker fallback.

## Architecture

```
QueryEngine
    |
    v
CacheManager (Circuit Breaker)
    |
    +-- RedisCacheStore (primary cache)
    +-- PostgresCacheStore (fallback)
```

## Usage

### Basic Usage

```python
from app.core.cache import get_cache_manager

# Get global instance
manager = await get_cache_manager(message_repo)

# Read session
session = await manager.get_session(conversation_id)

# Write session
await manager.set_session(conversation_id, {"messages": [...]}, ttl=3600)
```

### Monitoring Metrics

```python
from app.core.metrics.collector import global_collector

# Get cache statistics
stats = await global_collector.get_statistics("cache")
print(f"Hit rate: {stats['hit_rate']:.2%}")
print(f"Fallback count: {stats['fallback_count']}")
```

### Circuit Breaker State

```python
# Get circuit breaker state
state = manager.get_circuit_state()
stats = manager.get_circuit_stats()

print(f"State: {state}")  # closed, open, half_open
print(f"Failure count: {stats['failure_count']}")
```

## Configuration

Environment variables (in `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | localhost | Redis host |
| `REDIS_PORT` | 6379 | Redis port |
| `REDIS_PASSWORD` | None | Redis password |
| `REDIS_DB` | 0 | Redis database number |
| `REDIS_POOL_SIZE` | 20 | Connection pool size |
| `CACHE_CIRCUIT_THRESHOLD` | 5 | Failure threshold for circuit breaker |
| `CACHE_CIRCUIT_TIMEOUT` | 60 | Circuit breaker timeout (seconds) |

## TTL Values

| Data Type | TTL | Description |
|-----------|-----|-------------|
| Session | 3600s (1 hour) | Conversation history |
| Slots | 1800s (30 min) | Intent slots |
| User Prefs | 604800s (7 days) | User preferences |

All TTLs include ±10% random jitter to prevent cache stampede.

## Components

### ICacheStore
Abstract interface for cache stores. All stores must implement:
- `get_session()`, `set_session()`, `delete_session()`
- `get_slots()`, `set_slots()`, `delete_slots()`
- `get_user_prefs()`, `set_user_prefs()`, `delete_user_prefs()`
- `health_check()`

### RedisCacheStore
Primary cache store using Redis.
- Connection pooling
- PII data redaction before storage
- TTL with jitter

### PostgresCacheStore
Fallback store using existing MessageRepository.
- Read-only (writes go through existing persistence)
- Used when Redis is unavailable

### CacheManager
Unified cache entry point with circuit breaker.
- Automatic failover to Postgres
- Circuit breaker prevents cascading failures
- Metrics collection

### CircuitBreaker
Implements circuit breaker pattern.
- **CLOSED**: Normal operation, requests pass through
- **OPEN**: Failures exceeded threshold, requests blocked
- **HALF_OPEN**: Testing if Redis has recovered

## Error Handling

```python
from app.core.cache.errors import (
    CacheConnectionError,    # Triggers fallback
    CacheSerializationError,  # Triggers fallback
    CircuitOpenError,         # Uses fallback
    AllStoresFailedError,     # Critical error
)
```

## Testing

Run tests:
```bash
cd backend
pytest tests/core/test_cache/ -v
```

With coverage:
```bash
pytest tests/core/test_cache/ -v --cov=app/core/cache --cov-report=term-missing
```
