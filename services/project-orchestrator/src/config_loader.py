import yaml
import os
import logging # New import

logger = logging.getLogger(__name__) # New: Initialize logger

_CONFIG = {}

def load_config(config_path="config/base.yaml"):
    global _CONFIG
    absolute_config_path = os.path.join(os.getcwd(), config_path)
    
    logger.info(f"Attempting to load config from: {absolute_config_path}") # Debug log
    if not os.path.exists(absolute_config_path):
        logger.error(f"Configuration file not found at {absolute_config_path}. Current working directory: {os.getcwd()}") # Debug log
        raise FileNotFoundError(f"Configuration file not found at {absolute_config_path}")
        
    with open(absolute_config_path, 'r') as f:
        _CONFIG = yaml.safe_load(f)
    logger.info("Configuration loaded successfully.") # Debug log
    return _CONFIG

def get_config():
    return _CONFIG

if __name__ == "__main__":
    loaded_config = load_config()
    if loaded_config:
        print("Configuration loaded successfully:")
        print(loaded_config)
    else:
        print("Configuration not loaded.")
