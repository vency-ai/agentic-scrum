# Use the official Python image as the base image
FROM python:3.10-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file first to leverage Docker cache
COPY src/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application source code directly into the working directory
COPY src/ ./src

# Copy config file
COPY config/base.yaml ./src/config/base.yaml

# Set PYTHONPATH to include the src directory for imports
ENV PYTHONPATH=/app/src

# Set working directory to src for execution
WORKDIR /app/src

# Expose the port the application runs on
EXPOSE 80

# Command to run the application
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]
