import logging
from fastapi import FastAPI
from log_config import HealthCheckFilter
import uvicorn

app = FastAPI()

# Apply filter to Uvicorn access logger
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addFilter(HealthCheckFilter())

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/health/ready")
def ready():
    return {"status": "ready"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
