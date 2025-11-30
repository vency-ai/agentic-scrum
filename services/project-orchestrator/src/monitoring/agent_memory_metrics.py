from prometheus_client import Gauge, Counter, Histogram

# Agent Memory Database Connection Pool Metrics
AGENT_MEMORY_DB_POOL_SIZE = Gauge(
    'agent_memory_db_pool_size',
    'Current size of the agent memory database connection pool'
)
AGENT_MEMORY_DB_POOL_CHECKED_IN = Gauge(
    'agent_memory_db_pool_checked_in_connections',
    'Number of checked-in connections in the agent memory database connection pool'
)
AGENT_MEMORY_DB_POOL_CHECKED_OUT = Gauge(
    'agent_memory_db_pool_checked_out_connections',
    'Number of checked-out connections in the agent memory database connection pool'
)
AGENT_MEMORY_DB_POOL_OVERFLOW = Gauge(
    'agent_memory_db_pool_overflow_connections',
    'Number of overflow connections in the agent memory database connection pool'
)

# Embedding Service Metrics
EMBEDDING_GENERATION_LATENCY_SECONDS = Histogram(
    'embedding_generation_latency_seconds',
    'Latency of embedding generation requests',
    buckets=(.005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0, float('inf'))
)
EMBEDDING_GENERATION_FAILURES_TOTAL = Counter(
    'embedding_generation_failures_total',
    'Total number of failed embedding generation requests'
)
EMBEDDING_SERVICE_CIRCUIT_BREAKER_STATE = Gauge(
    'embedding_service_circuit_breaker_state',
    'Current state of the embedding service circuit breaker (0=CLOSED, 1=OPEN, 0.5=HALF_OPEN)'
)

# Agent Memory Database Operation Metrics
AGENT_MEMORY_DB_OPERATION_LATENCY_SECONDS = Histogram(
    'agent_memory_db_operation_latency_seconds',
    'Latency of agent memory database operations',
    ['operation'],
    buckets=(.001, .005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, float('inf'))
)
AGENT_MEMORY_DB_OPERATION_FAILURES_TOTAL = Counter(
    'agent_memory_db_operation_failures_total',
    'Total number of failed agent memory database operations',
    ['operation']
)

# Embedding Backfill Service Metrics
EMBEDDING_BACKFILL_EPISODES_PROCESSED_TOTAL = Counter(
    'embedding_backfill_episodes_processed_total',
    'Total number of episodes processed by backfill service',
    ['result']  # success, failed, skipped
)
EMBEDDING_BACKFILL_RUN_DURATION_SECONDS = Histogram(
    'embedding_backfill_run_duration_seconds',
    'Duration of complete backfill runs',
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, float('inf'))
)
EMBEDDING_BACKFILL_EPISODES_PENDING = Gauge(
    'embedding_backfill_episodes_pending',
    'Current number of episodes without embeddings'
)
EMBEDDING_BACKFILL_LAST_RUN_TIMESTAMP = Gauge(
    'embedding_backfill_last_run_timestamp',
    'Unix timestamp of the last successful backfill run'
)
EMBEDDING_BACKFILL_BATCH_SIZE = Gauge(
    'embedding_backfill_batch_size',
    'Current batch size for backfill operations'
)
