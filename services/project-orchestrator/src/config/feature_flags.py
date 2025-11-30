import os
from typing import Dict, Any
from config_loader import get_config

class FeatureFlags:
    def __init__(self):
        self._config = get_config().get("intelligence", {}).get("feature_flags", {})

    def get_flag(self, flag_name: str, default_value: Any = False) -> Any:
        # Environment variables take precedence
        env_var_name = f"FEATURE_FLAG_{flag_name.upper()}"
        if env_var_name in os.environ:
            env_value = os.environ.get(env_var_name, str(default_value)).lower()
            if env_value == "true":
                return True
            elif env_value == "false":
                return False
            else:
                return env_value # Allow other types if needed

        # Fallback to config file
        return self._config.get(flag_name, default_value)

    @property
    def ENABLE_ASYNC_LEARNING(self) -> bool:
        return self.get_flag("enable_async_learning", False)

    @property
    def ENABLE_STRATEGY_EVOLUTION(self) -> bool:
        return self.get_flag("enable_strategy_evolution", False)

    @property
    def ENABLE_CROSS_PROJECT_LEARNING(self) -> bool:
        return self.get_flag("enable_cross_project_learning", False)

    @property
    def ENABLE_EPISODIC_MEMORY(self) -> bool:
        return self.get_flag("enable_episodic_memory", False)

    @property
    def ENABLE_WORKING_MEMORY(self) -> bool:
        return self.get_flag("enable_working_memory", False)

    @property
    def ENABLE_KNOWLEDGE_STORE(self) -> bool:
        return self.get_flag("enable_knowledge_store", False)

feature_flags = FeatureFlags()
