from typing import List, Dict, Any, Optional
import structlog
from datetime import datetime

from intelligence.chronicle_analytics_client import ChronicleAnalyticsClient, ProjectPatterns, VelocityData, ImpedimentAnalysis # Import Pydantic models

logger = structlog.get_logger()

# Remove the custom ProjectPatterns, VelocityTrend, ImpedimentAnalysis classes
# and use the Pydantic models from chronicle_analytics_client.py directly.

class HistoricalAnalyzer:
    def __init__(self, chronicle_analytics_client: ChronicleAnalyticsClient):
        self.chronicle_analytics_client = chronicle_analytics_client

    async def analyze_project_patterns(self, project_id: str) -> ProjectPatterns:
        """Analyzes historical patterns for a given project."""
        try:
            patterns_data = await self.chronicle_analytics_client.get_project_patterns(project_id)
            velocity_data = await self.chronicle_analytics_client.get_velocity_trends(project_id) # Use get_velocity_trends
            impediments_data = await self.chronicle_analytics_client.get_project_impediments(project_id) # Corrected method call

            # Initialize with data from patterns_data if available
            project_patterns = patterns_data if patterns_data else ProjectPatterns(project_id=project_id)

            # Update project_patterns with additional derived data or data from other analytics endpoints
            avg_sprint_duration = 0.0
            completion_rate = 0.0
            velocity_trend = velocity_data.velocity_analysis if velocity_data else "unknown"
            common_impediments = list(impediments_data.impediment_frequency.keys()) if impediments_data and impediments_data.impediment_frequency else []

            # Calculate average sprint duration and completion rate from velocity data
            if velocity_data and velocity_data.velocity_trend_data:
                total_duration_days = 0
                total_sprints = 0
                total_completed_tasks = 0
                total_tasks_in_sprints = 0 # This would ideally come from sprint planning notes or backlog at sprint start

                for sprint in velocity_data.velocity_trend_data:
                    start_date_str = sprint.start_date
                    end_date_str = sprint.end_date
                    completed_tasks = sprint.completed_tasks

                    if start_date_str and end_date_str:
                        try:
                            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                            duration = (end_date - start_date).days
                            total_duration_days += duration
                            total_sprints += 1
                            total_completed_tasks += completed_tasks
                            # Placeholder for total tasks in sprint - needs actual data
                            total_tasks_in_sprints += completed_tasks # Assuming all tasks in sprint are completed for now
                        except ValueError as e:
                            logger.warning("Could not parse sprint dates", sprint_id=sprint.sprint_id, error=str(e))

                if total_sprints > 0:
                    avg_sprint_duration = (total_duration_days / total_sprints) / 7 # in weeks
                if total_tasks_in_sprints > 0: # Avoid division by zero
                    completion_rate = total_completed_tasks / total_tasks_in_sprints

            # Update the ProjectPatterns object with calculated values
            if patterns_data:
                project_patterns.daily_scrum_count = patterns_data.daily_scrum_count
                project_patterns.retrospective_count = patterns_data.retrospective_count
                project_patterns.total_tasks_completed_in_daily_scrums = patterns_data.total_tasks_completed_in_daily_scrums
                project_patterns.common_retrospective_action_items = patterns_data.common_retrospective_action_items
                project_patterns.patterns_analysis_summary = patterns_data.patterns_analysis_summary

            return project_patterns
        except Exception as e:
            logger.error("Error analyzing project patterns", project_id=project_id, error=str(e))
            return ProjectPatterns(project_id=project_id) # Return default Pydantic model on error

    async def calculate_velocity_trends(self, project_id: str) -> VelocityData:
        """Calculates team velocity trends for a given project."""
        try:
            velocity_data = await self.chronicle_analytics_client.get_velocity_trends(project_id)
            return velocity_data if velocity_data else VelocityData(project_id=project_id)
        except Exception as e:
            logger.error("Error calculating velocity trends", project_id=project_id, error=str(e))
            return VelocityData(project_id=project_id) # Return default on error

    async def extract_impediment_patterns(self, project_id: str) -> ImpedimentAnalysis:
        """Extracts common impediment patterns for a given project."""
        try:
            impediments_data = await self.chronicle_analytics_client.get_project_impediments(project_id)
            return impediments_data if impediments_data else ImpedimentAnalysis(project_id=project_id)
        except Exception as e:
            logger.error("Error extracting impediment patterns", project_id=project_id, error=str(e))
            return ImpedimentAnalysis(project_id=project_id) # Return default on error
