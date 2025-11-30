# Use a Python base image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project, excluding .venv and __pycache__
COPY . .

# Set PYTHONPATH to include the src directory
ENV PYTHONPATH=/app/src

# Command to run the tests
CMD ["python", "-m", "unittest", "tests/test_orchestrator.py"]