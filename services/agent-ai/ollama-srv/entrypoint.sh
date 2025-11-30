#!/bin/bash

# Start Ollama server in background just to pull models
echo "📦 Pulling models from models.json..."
ollama serve &
OLLAMA_PID=$!

# Wait a bit for the Ollama server to become ready
sleep 5

# Pull each model from JSON
jq -r '.models[]' models.json | while read model; do
  echo "📥 Pulling model: $model"
  ollama pull "$model"
done

# Stop the temporary background Ollama
kill $OLLAMA_PID
wait $OLLAMA_PID 2>/dev/null

echo "🚀 Starting Ollama server in foreground..."
# This keeps container logs active and useful
exec ollama serve
