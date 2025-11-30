import psutil
import time
from typing import Dict

class ResourceMonitor:
    def __init__(self):
        self.process = psutil.Process()
        self.baseline_memory = self.process.memory_info().rss
    
    def get_resource_usage(self) -> Dict:
        memory_info = self.process.memory_info()
        cpu_percent = self.process.cpu_percent()
        
        return {
            "memory_usage_mb": memory_info.rss / 1024 / 1024,
            "memory_increase_mb": (memory_info.rss - self.baseline_memory) / 1024 / 1024,
            "cpu_percent": cpu_percent,
            "open_files": len(self.process.open_files()),
            "threads": self.process.num_threads()
        }
    
    def check_memory_threshold(self, max_increase_mb: int = 100) -> bool:
        current_increase = (self.process.memory_info().rss - self.baseline_memory) / 1024 / 1024
        return current_increase <= max_increase_mb
