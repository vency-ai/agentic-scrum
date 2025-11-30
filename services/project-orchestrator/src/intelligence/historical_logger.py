import structlog
from typing import Dict, Any, List, Optional

logger = structlog.get_logger()

class HistoricalLogger:
    def __init__(self):
        self.data_usage_patterns: Dict[str, Dict[str, int]] = {}
        logger.info("HistoricalLogger initialized.")

    def log_decision_with_historical_context(self, project_id: str, decision: Dict[str, Any], historical_data: Dict[str, Any]):
        """Logs an orchestration decision along with relevant historical context."""
        log_context = {
            "project_id": project_id,
            "decision": decision,
            "historical_context": historical_data
        }
        logger.info("Orchestration decision made with historical context.", **log_context)

    def create_observation_summary(self, historical_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a concise summary of historical observations for the API response."""
        summary = {
            "data_available": bool(historical_data),
            "historical_sprints": None,
            "avg_completion_rate": None,
            "common_team_velocity": None,
            "data_quality_score": None,
            "observation_note": "No significant historical data found."
        }

        if historical_data:
            summary["observation_note"] = "Historical data retrieved."
            if historical_data.get("project_patterns"):
                patterns = historical_data["project_patterns"]
                summary["historical_sprints"] = patterns.daily_scrum_count # Using daily_scrum_count as a proxy
                summary["avg_completion_rate"] = patterns.total_tasks_completed_in_daily_scrums # Placeholder
                if patterns.patterns_analysis_summary:
                    summary["observation_note"] += f" Patterns: {patterns.patterns_analysis_summary}"

            if historical_data.get("velocity_data"):
                velocity = historical_data["velocity_data"]
                summary["common_team_velocity"] = velocity.average_velocity
                if velocity.velocity_analysis:
                    summary["observation_note"] += f" Velocity: {velocity.velocity_analysis}"
            
            if historical_data.get("data_quality_report"):
                summary["data_quality_score"] = historical_data["data_quality_report"].data_quality_score
                if historical_data["data_quality_report"].observation_note:
                    summary["observation_note"] += f" Quality: {historical_data['data_quality_report'].observation_note}"

        logger.debug("Historical observation summary created.", summary=summary)
        return summary

    def track_data_usage_patterns(self, project_id: str, data_types: List[str]):
        """Tracks which types of historical data are being used for a given project."""
        if project_id not in self.data_usage_patterns:
            self.data_usage_patterns[project_id] = {}
        
        for data_type in data_types:
            self.data_usage_patterns[project_id][data_type] = self.data_usage_patterns[project_id].get(data_type, 0) + 1
        
        logger.debug("Data usage patterns tracked.", project_id=project_id, data_types=data_types, patterns=self.data_usage_patterns[project_id])

    def get_data_usage_patterns(self, project_id: str) -> Dict[str, int]:
        """Retrieves the data usage patterns for a specific project."""
        return self.data_usage_patterns.get(project_id, {})
