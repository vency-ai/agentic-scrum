import numpy as np
from typing import List, Dict, Any, Optional
from sklearn.metrics.pairwise import cosine_similarity
from models import ProjectCharacteristics, SimilarProject, ProjectData # Absolute import
import structlog

logger = structlog.get_logger()

def extract_project_characteristics(project_data: Dict[str, Any]) -> ProjectCharacteristics:
    """Extracts relevant characteristics from project data for similarity calculation."""
    # Placeholder for actual extraction logic. This will need to be refined based on available data.
    # For now, using dummy values or direct mapping from ProjectData if available.
    project_id = project_data.get("project_id", "unknown")
    team_size = project_data.get("team_size", 0)
    # Assuming avg_task_complexity, domain_category, project_duration are available or can be derived
    # For now, using placeholders. These would ideally come from Chronicle analytics or other services.
    avg_task_complexity = project_data.get("avg_task_complexity", 0.5) # Placeholder
    domain_category = project_data.get("domain_category", "general") # Placeholder
    project_duration = project_data.get("project_duration", 0.0) # Placeholder

    return ProjectCharacteristics(
        project_id=project_id,
        team_size=team_size,
        avg_task_complexity=avg_task_complexity,
        domain_category=domain_category,
        project_duration=project_duration
    )

def _normalize_characteristics(characteristics: ProjectCharacteristics) -> np.ndarray:
    """Normalizes project characteristics into a numerical vector."""
    # This is a simplified normalization. In a real scenario, 'domain_category' would need
    # one-hot encoding or embedding. For now, we'll assign a numerical value.
    domain_map = {"general": 0.5, "frontend": 0.2, "backend": 0.8, "database": 0.9}
    domain_val = domain_map.get(characteristics.domain_category.lower(), 0.5)

    # Simple normalization for numerical features (min-max scaling conceptual)
    # Assuming max values for scaling for now. These should be dynamic or configured.
    max_team_size = 20
    max_avg_task_complexity = 1.0
    max_project_duration = 52.0 # 1 year

    normalized_team_size = characteristics.team_size / max_team_size if max_team_size > 0 else 0
    normalized_avg_task_complexity = characteristics.avg_task_complexity / max_avg_task_complexity if max_avg_task_complexity > 0 else 0
    normalized_project_duration = characteristics.project_duration / max_project_duration if max_project_duration > 0 else 0

    return np.array([
        normalized_team_size,
        normalized_avg_task_complexity,
        domain_val, # Simplified
        normalized_project_duration
    ])

def calculate_project_similarity(project1: ProjectCharacteristics, project2: ProjectCharacteristics) -> float:
    """Calculates the cosine similarity between two projects based on their characteristics."""
    vec1 = _normalize_characteristics(project1)
    vec2 = _normalize_characteristics(project2)

    if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
        return 0.0 # Avoid division by zero if a vector is all zeros

    return cosine_similarity(vec1.reshape(1, -1), vec2.reshape(1, -1))[0][0]

async def find_similar_projects(target_project_data: ProjectData, all_projects_data: List[Dict[str, Any]], threshold: float = 0.7) -> List[SimilarProject]:
    """Finds projects similar to the target project from a list of all projects."""
    logger.info("Finding similar projects", target_project_id=target_project_data.project_id, threshold=threshold)
    target_characteristics = extract_project_characteristics(target_project_data.dict())
    similar_projects_list: List[SimilarProject] = []

    for project_data_dict in all_projects_data:
        if project_data_dict.get("project_id") == target_project_data.project_id:
            continue # Don't compare a project to itself

        other_characteristics = extract_project_characteristics(project_data_dict)
        similarity = calculate_project_similarity(target_characteristics, other_characteristics)

        if similarity >= threshold:
            # Placeholder for extracting actual success factors, completion rate, avg sprint duration
            # These would come from Chronicle analytics for the similar project
            similar_projects_list.append(SimilarProject(
                project_id=other_characteristics.project_id,
                similarity_score=round(similarity, 4),
                team_size=other_characteristics.team_size,
                completion_rate=project_data_dict.get("completion_rate", 0.0), # Placeholder
                avg_sprint_duration=project_data_dict.get("avg_sprint_duration", 0.0), # Placeholder
                key_success_factors=project_data_dict.get("key_success_factors", []) # Placeholder
            ))
    
    logger.info("Found similar projects", count=len(similar_projects_list))
    logger.debug("Normalized characteristics", project_id=characteristics.project_id, vector=normalized_vector.tolist())
    return normalized_vector

def calculate_project_similarity(project1: ProjectCharacteristics, project2: ProjectCharacteristics) -> float:
    """Calculates the cosine similarity between two projects based on their characteristics."""
    vec1 = _normalize_characteristics(project1)
    vec2 = _normalize_characteristics(project2)

    if np.linalg.norm(vec1) == 0 or np.linalg.norm(vec2) == 0:
        logger.debug("One or both vectors are zero, returning 0.0 similarity.", project1_id=project1.project_id, project2_id=project2.project_id)
        return 0.0

    similarity = cosine_similarity(vec1.reshape(1, -1), vec2.reshape(1, -1))[0][0]
    logger.debug("Calculated similarity", project1_id=project1.project_id, project2_id=project2.project_id, similarity=similarity)
    return similarity

async def find_similar_projects(target_project_data: ProjectData, all_projects_data: List[Dict[str, Any]], threshold: float = 0.7) -> List[SimilarProject]:
    """Finds projects similar to the target project from a list of all projects."""
    logger.info("Finding similar projects", target_project_id=target_project_data.project_id, threshold=threshold)
    target_characteristics = extract_project_characteristics(target_project_data.dict())
    logger.debug("Target project characteristics", characteristics=target_characteristics.dict())
    similar_projects_list: List[SimilarProject] = []

    for project_data_dict in all_projects_data:
        if project_data_dict.get("project_id") == target_project_data.project_id:
            logger.debug("Skipping self-comparison", project_id=target_project_data.project_id)
            continue

        other_characteristics = extract_project_characteristics(project_data_dict)
        logger.debug("Comparing with project characteristics", other_project_id=other_characteristics.project_id, characteristics=other_characteristics.dict())
        similarity = calculate_project_similarity(target_characteristics, other_characteristics)

        if similarity >= threshold:
            logger.info("Found similar project above threshold", project_id=other_characteristics.project_id, similarity=similarity, threshold=threshold)
            similar_projects_list.append(SimilarProject(
                project_id=other_characteristics.project_id,
                similarity_score=round(similarity, 4),
                team_size=other_characteristics.team_size,
                completion_rate=project_data_dict.get("completion_rate", 0.0),
                avg_sprint_duration=project_data_dict.get("avg_sprint_duration", 0.0),
                key_success_factors=project_data_dict.get("key_success_factors", [])
            ))
    
    logger.info("Found similar projects", count=len(similar_projects_list))
    return similar_projects_list
