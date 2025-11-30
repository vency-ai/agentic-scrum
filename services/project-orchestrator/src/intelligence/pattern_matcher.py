from typing import List, Dict, Any, Optional
import structlog
from pydantic import BaseModel, Field

from intelligence.chronicle_analytics_client import ChronicleAnalyticsClient
from intelligence.historical_analyzer import ProjectPatterns

logger = structlog.get_logger()

class SimilarProject(BaseModel):
    project_id: str
    similarity_score: float
    success_rate: float = 0.0
    lessons_learned: List[str] = Field(default_factory=list)

class SuccessPatterns(BaseModel):
    common_success_factors: List[str] = Field(default_factory=list)
    common_mitigations: List[str] = Field(default_factory=list)

class Recommendation(BaseModel):
    description: str
    category: str

class PatternMatcher:
    def __init__(self, chronicle_analytics_client: ChronicleAnalyticsClient):
        self.chronicle_analytics_client = chronicle_analytics_client

    async def find_similar_projects(self, reference_project_id: str, similarity_threshold: float = 0.7) -> List[SimilarProject]:
        """Finds projects with similar characteristics based on historical data."""
        try:
            similar_projects_data = await self.chronicle_analytics_client.get_similar_projects(reference_project_id, similarity_threshold)
            
            similar_projects = []
            if similar_projects_data:
                for sp_data in similar_projects_data:
                    # For simplicity, success_rate and lessons_learned are placeholders or derived from further analysis
                    # In a real scenario, this would involve fetching more detailed data for each similar project
                    similar_projects.append(SimilarProject(
                        project_id=sp_data["project_id"],
                        similarity_score=sp_data["similarity_score"],
                        success_rate=sp_data.get("success_rate", 0.0), # Use .get for optional fields
                        lessons_learned=sp_data.get("lessons_learned", []) # Use .get for optional fields
                    ))
            return similar_projects
        except Exception as e:
            logger.error("Error finding similar projects", project_id=reference_project_id, error=str(e))
            return []

    async def extract_success_patterns(self, similar_projects: List[SimilarProject]) -> SuccessPatterns:
        """Extracts common success patterns from a list of similar projects."""
        # This is a placeholder for more complex logic that would analyze retrospectives
        # and other historical data from similar projects to find common success factors.
        common_success_factors = ["early_integration_testing", "daily_stakeholder_sync"] # Example
        common_mitigations = ["monitor_dependency_blockers"] # Example
        return SuccessPatterns(common_success_factors=common_success_factors, common_mitigations=common_mitigations)

    async def generate_recommendations(self, patterns: SuccessPatterns) -> List[Recommendation]:
        """Generates recommendations based on extracted success patterns."""
        recommendations = []
        for factor in patterns.common_success_factors:
            recommendations.append(Recommendation(description=f"Consider implementing {factor}.", category="Best Practice"))
        for mitigation in patterns.common_mitigations:
            recommendations.append(Recommendation(description=f"Implement {mitigation} to reduce risk.", category="Risk Mitigation"))
        return recommendations