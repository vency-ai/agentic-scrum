# pull_models.py
import json
import subprocess

CONFIG_FILE = "models.json"
OLLAMA_BIN = "/root/.ollama/bin/ollama"
def pull_models():
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
        models = data.get("models", [])

    for model in models:
        print(f"📦 Pulling model: {model}")
        #result = subprocess.run(["ollama", "pull", model], capture_output=True, text=True)
        result = subprocess.run([OLLAMA_BIN, "pull", model], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Failed to pull {model}: {result.stderr}")
        else:
            print(f"✅ Pulled {model}")

if __name__ == "__main__":
    pull_models()
