import logging

class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Filter out /health and /health/ready access logs
        return not (record.getMessage().find("/health") != -1 or record.getMessage().find("/health/ready") != -1)