import structlog
from typing import Dict, Any, List, Optional
from intelligence.chronicle_analytics_client import DataQualityReport

logger = structlog.get_logger()

class DataQualityValidator:
    def __init__(self):
        logger.info("DataQualityValidator initialized.")

    def assess_data_quality(self, historical_data: Dict[str, Any]) -> float:
        """Assess the overall quality of historical data based on completeness and consistency."""
        score = 0.0
        present_fields = 0
        expected_fields = 0

        # Example: Check for presence of key analytics data
        if historical_data.get("project_patterns"):
            patterns = historical_data["project_patterns"]
            expected_fields += 4 # project_id, daily_scrum_count, retrospective_count, patterns_analysis_summary
            if patterns.get("project_id"): present_fields += 1
            if patterns.get("daily_scrum_count") is not None: present_fields += 1
            if patterns.get("retrospective_count") is not None: present_fields += 1
            if patterns.get("patterns_analysis_summary"): present_fields += 1

        if historical_data.get("velocity_data"):
            velocity = historical_data["velocity_data"]
            expected_fields += 3 # project_id, velocity_trend_data, average_velocity
            if velocity.get("project_id"): present_fields += 1
            if velocity.get("velocity_trend_data"): present_fields += 1
            if velocity.get("average_velocity") is not None: present_fields += 1

        if expected_fields > 0:
            score = (present_fields / expected_fields) * 100

        logger.debug("Data quality assessed.", score=score, present_fields=present_fields, expected_fields=expected_fields)
        return round(score, 2)

    def validate_data_completeness(self, historical_data: Dict[str, Any]) -> Dict[str, Any]:
        """Provides a report on the completeness of various historical data points."""
        completeness_report = {
            "project_patterns_available": bool(historical_data.get("project_patterns")),
            "velocity_data_available": bool(historical_data.get("velocity_data")),
            "sprint_history_available": bool(historical_data.get("sprint_history")),
            "has_sufficient_sprints": len(historical_data.get("sprint_history", [])) >= 3 # Example threshold
        }
        logger.debug("Data completeness validated.", report=completeness_report)
        return completeness_report

    def recommend_data_improvements(self, quality_report: DataQualityReport) -> List[str]:
        """Generates recommendations based on the data quality report."""
        recommendations = []
        if not quality_report.data_available:
            recommendations.append("No historical data found. Ensure Chronicle Service is running and has processed data for this project.")
        if quality_report.historical_sprints is None or quality_report.historical_sprints < 3:
            recommendations.append("Insufficient sprint history. Run more sprints to generate richer historical data.")
        if quality_report.avg_completion_rate is None:
            recommendations.append("Average completion rate not available. Ensure tasks are being marked as completed.")
        if quality_report.common_team_velocity is None:
            recommendations.append("Team velocity data not available. Ensure sprint tasks are being tracked and completed.")
        
        logger.debug("Data improvement recommendations generated.", recommendations=recommendations)
        return recommendations
