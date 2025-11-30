# Stage 1: Builder - To install dependencies
FROM python:3.9-slim-buster AS builder

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Install dependencies globally
COPY src/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Stage 2: Final Image - To run the application
FROM python:3.9-slim-buster

# Create a non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Set the working directory
WORKDIR /app

# Copy the application source code
RUN echo "Force cache invalidation for app.py $(date +%s)"
COPY --chown=appuser:appuser src/app.py /app/app.py
RUN echo "Force cache invalidation for log_config.py $(date +%s)"
COPY --chown=appuser:appuser src/log_config.py /app/log_config.py
COPY --chown=appuser:appuser src/event_consumer.py /app/event_consumer.py
COPY --chown=appuser:appuser src/utils.py /app/utils.py
RUN echo "Force cache invalidation for analytics modules $(date +%s)"
COPY --chown=appuser:appuser src/analytics_engine.py /app/analytics_engine.py
COPY --chown=appuser:appuser src/analytics_router.py /app/analytics_router.py
COPY --chown=appuser:appuser src/database.py /app/database.py

# Copy requirements.txt to the app directory
COPY --chown=appuser:appuser src/requirements.txt /app/requirements.txt

# Switch to the non-root user
USER appuser

# Set PATH for non-root user to include pip-installed executables
ENV PATH="/home/appuser/.local/bin:$PATH"

# Install dependencies as appuser in the final stage
RUN pip install --no-cache-dir -r /app/requirements.txt

# Expose the port the application will run on
EXPOSE 80

# Command to run the application (uvicorn is now in the system PATH)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]
