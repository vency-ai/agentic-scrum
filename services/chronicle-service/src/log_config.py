import logging
import structlog

class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Filter out /health and /health/ready access logs
        return not (record.getMessage().find("/health") != -1 or record.getMessage().find("/health/ready") != -1)

# Configure structlog to output DEBUG level messages
structlog.configure(
    processors=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"), # Add timestamp for better debugging
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(), # Use ConsoleRenderer for development, JSONRenderer for production
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logging.basicConfig(
    format="%(message)s",
    level=logging.DEBUG,
    handlers=[
        logging.StreamHandler()
    ]
)

# Explicitly set the level for the structlog logger factory
structlog.get_logger().setLevel(logging.DEBUG)

# Also set the level for the root logger and uvicorn loggers
logging.getLogger().setLevel(logging.DEBUG)
logging.getLogger("uvicorn").setLevel(logging.DEBUG)
logging.getLogger("uvicorn.access").setLevel(logging.DEBUG)
logging.getLogger("uvicorn.error").setLevel(logging.DEBUG)