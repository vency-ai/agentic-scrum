from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import aiohttp
import asyncio
import time
import logging
from typing import List

app = FastAPI(title="Embedding Proxy Service", version="1.0.0")

# Configuration
OLLAMA_BASE_URL = "http://ollama-server.dsm.svc.cluster.local:11434"
OLLAMA_MODEL = "mxbai-embed-large:latest"

# Metrics storage
metrics = {
    "total_requests": 0,
    "total_embeddings": 0,
    "ollama_errors": 0,
    "latencies": []
}

# HTTP client session
http_session = None

@app.on_event("startup")
async def startup_event():
    global http_session
    http_session = aiohttp.ClientSession()
    logging.info(f"Embedding proxy service started, connecting to {OLLAMA_BASE_URL}")

@app.on_event("shutdown")
async def shutdown_event():
    if http_session:
        await http_session.close()

class EmbedRequest(BaseModel):
    text: str

class BatchEmbedRequest(BaseModel):
    texts: List[str]

async def call_ollama_embedding(text: str) -> List[float]:
    """Call Ollama API for single embedding"""
    try:
        async with http_session.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": OLLAMA_MODEL, "prompt": text},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            if response.status != 200:
                raise HTTPException(status_code=503, 
                                  detail=f"Ollama API error: {response.status}")
            
            result = await response.json()
            return result["embedding"]
    except asyncio.TimeoutError:
        metrics["ollama_errors"] += 1
        raise HTTPException(status_code=503, detail="Ollama API timeout")
    except Exception as e:
        metrics["ollama_errors"] += 1
        raise HTTPException(status_code=503, 
                          detail=f"Ollama API unavailable: {str(e)}")

@app.post("/embed")
async def generate_embedding(request: EmbedRequest):
    start_time = time.time()
    
    try:
        embedding = await call_ollama_embedding(request.text)
        generation_time = (time.time() - start_time) * 1000
        
        # Update metrics
        metrics["total_requests"] += 1
        metrics["total_embeddings"] += 1
        metrics["latencies"].append(generation_time)
        if len(metrics["latencies"]) > 1000:
            metrics["latencies"] = metrics["latencies"][-1000:]
        
        return {
            "embedding": embedding,
            "dimensions": len(embedding),
            "model": OLLAMA_MODEL,
            "generation_time_ms": round(generation_time, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, 
                          detail=f"Embedding generation failed: {str(e)}")

@app.post("/embed/batch")
async def generate_batch_embeddings(request: BatchEmbedRequest):
    start_time = time.time()
    
    try:
        # Generate embeddings concurrently for better performance
        tasks = [call_ollama_embedding(text) for text in request.texts]
        embeddings = await asyncio.gather(*tasks)
        
        total_time = (time.time() - start_time) * 1000
        
        # Update metrics
        metrics["total_requests"] += 1
        metrics["total_embeddings"] += len(request.texts)
        metrics["latencies"].append(total_time / len(request.texts))
        
        return {
            "embeddings": embeddings,
            "count": len(embeddings),
            "dimensions": len(embeddings[0]) if embeddings else 0,
            "model": OLLAMA_MODEL,
            "total_time_ms": round(total_time, 2)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, 
                          detail=f"Batch embedding failed: {str(e)}")

@app.get("/health")
async def health_check():
    try:
        # Quick health check to Ollama
        async with http_session.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=aiohttp.ClientTimeout(total=5)
        ) as response:
            ollama_available = response.status == 200
            
            if not ollama_available:
                raise HTTPException(status_code=503, 
                                  detail="Ollama server unavailable")
    except Exception:
        raise HTTPException(status_code=503, 
                          detail="Cannot connect to Ollama server")
    
    return {
        "status": "healthy",
        "ollama_available": True,
        "model_name": OLLAMA_MODEL,
        "ollama_endpoint": OLLAMA_BASE_URL
    }

@app.get("/metrics")
async def get_metrics():
    if not metrics["latencies"]:
        avg_latency = 0
        p95_latency = 0
    else:
        avg_latency = sum(metrics["latencies"]) / len(metrics["latencies"])
        sorted_latencies = sorted(metrics["latencies"])
        p95_index = int(len(sorted_latencies) * 0.95)
        p95_latency = sorted_latencies[p95_index] if sorted_latencies else 0
    
    return {
        "total_requests": metrics["total_requests"],
        "total_embeddings_generated": metrics["total_embeddings"],
        "avg_latency_ms": round(avg_latency, 2),
        "p95_latency_ms": round(p95_latency, 2),
        "ollama_errors": metrics["ollama_errors"],
        "uptime_seconds": int(time.time() - start_time) if 'start_time' in globals() else 0
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
