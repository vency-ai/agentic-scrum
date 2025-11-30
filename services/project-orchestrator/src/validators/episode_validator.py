"""
Episode Validator

Provides quality scoring and validation for episodes to ensure only high-quality
episodes are used for learning purposes.
"""

import logging
from typing import Dict, Any, List, Tuple
from memory.models import Episode

logger = logging.getLogger(__name__)

class EpisodeValidator:
    """
    Validates and scores episodes for quality assessment.
    
    Quality scoring is based on:
    - Context completeness (perception data richness)
    - Reasoning completeness (decision logic clarity)
    - Action completeness (execution details)
    - Outcome availability (learning value)
    """
    
    def __init__(self, quality_threshold: float = 0.7):
        """
        Initialize the episode validator.
        
        Args:
            quality_threshold: Minimum quality score for episodes to be used in learning
        """
        self.quality_threshold = quality_threshold
        
    def validate_episode(self, episode: Episode) -> Tuple[bool, float, List[str]]:
        """
        Validate an episode and return quality assessment.
        
        Args:
            episode: Episode to validate
            
        Returns:
            Tuple of (is_valid, quality_score, issues_list)
        """
        quality_score, issues = self._calculate_quality_score(episode)
        is_valid = quality_score >= self.quality_threshold
        
        logger.debug(
            f"Episode validation for {episode.project_id}: "
            f"score={quality_score:.2f}, valid={is_valid}, issues={len(issues)}"
        )
        
        return is_valid, quality_score, issues
    
    def _calculate_quality_score(self, episode: Episode) -> Tuple[float, List[str]]:
        """
        Calculate quality score for an episode.
        
        Scoring breakdown:
        - Perception quality: 30% (context richness)
        - Reasoning quality: 30% (decision clarity)
        - Action quality: 25% (execution completeness)
        - Outcome quality: 15% (learning value)
        """
        issues = []
        scores = {}
        
        # Perception quality (30%)
        perception_score = self._score_perception(episode.perception, issues)
        scores['perception'] = perception_score * 0.30
        
        # Reasoning quality (30%)
        reasoning_score = self._score_reasoning(episode.reasoning, issues)
        scores['reasoning'] = reasoning_score * 0.30
        
        # Action quality (25%)
        action_score = self._score_action(episode.action, issues)
        scores['action'] = action_score * 0.25
        
        # Outcome quality (15%)
        outcome_score = self._score_outcome(episode, issues)
        scores['outcome'] = outcome_score * 0.15
        
        total_score = sum(scores.values())
        
        logger.debug(f"Episode quality breakdown: {scores}, total: {total_score:.2f}")
        
        return total_score, issues
    
    def _score_perception(self, perception: Dict[str, Any], issues: List[str]) -> float:
        """Score the perception (context) quality."""
        if not perception:
            issues.append("Missing perception data")
            return 0.0
        
        score = 0.0
        max_score = 1.0
        
        # Check for essential context fields
        essential_fields = [
            'project_data',
            'backlog_summary', 
            'team_availability',
            'current_sprint_status'
        ]
        
        present_fields = 0
        for field in essential_fields:
            if field in perception and perception[field]:
                present_fields += 1
                score += 0.2  # Each essential field worth 20%
        
        # Check for data richness
        if 'project_data' in perception:
            project_data = perception['project_data']
            if isinstance(project_data, dict):
                # Bonus for detailed project data
                if len(project_data) > 3:
                    score += 0.1
                # Check for team info
                if 'team_size' in project_data and project_data['team_size']:
                    score += 0.1
        
        if present_fields < len(essential_fields) // 2:
            issues.append(f"Limited context data: only {present_fields}/{len(essential_fields)} essential fields present")
        
        return min(score, max_score)
    
    def _score_reasoning(self, reasoning: Dict[str, Any], issues: List[str]) -> float:
        """Score the reasoning quality."""
        if not reasoning:
            issues.append("Missing reasoning data")
            return 0.0
        
        score = 0.0
        max_score = 1.0
        
        # Check for reasoning components
        reasoning_fields = [
            'analysis_performed',
            'patterns_identified',
            'confidence_scores',
            'decision_rationale'
        ]
        
        present_fields = 0
        for field in reasoning_fields:
            if field in reasoning and reasoning[field]:
                present_fields += 1
                score += 0.2  # Each reasoning field worth 20%
        
        # Check for confidence information
        if 'confidence_scores' in reasoning:
            confidence_data = reasoning['confidence_scores']
            if isinstance(confidence_data, dict) and confidence_data:
                score += 0.1  # Bonus for confidence data
        
        # Check for pattern analysis
        if 'patterns_identified' in reasoning:
            patterns = reasoning['patterns_identified']
            if isinstance(patterns, (list, dict)) and patterns:
                score += 0.1  # Bonus for pattern analysis
        
        if present_fields < 2:
            issues.append(f"Insufficient reasoning detail: only {present_fields} reasoning components")
        
        return min(score, max_score)
    
    def _score_action(self, action: Dict[str, Any], issues: List[str]) -> float:
        """Score the action completeness."""
        if not action:
            issues.append("Missing action data")
            return 0.0
        
        score = 0.0
        max_score = 1.0
        
        # Check for action components
        action_types = ['sprint_created', 'tasks_assigned', 'adjustments_made', 'cronjob_created']
        actions_taken = 0
        
        for action_type in action_types:
            if action_type in action and action[action_type]:
                actions_taken += 1
                score += 0.2  # Each action type worth 20%
        
        # Check for detailed action data
        if 'sprint_created' in action and action['sprint_created']:
            sprint_data = action['sprint_created']
            if isinstance(sprint_data, dict) and 'sprint_id' in sprint_data:
                score += 0.1  # Bonus for detailed sprint creation
        
        if 'tasks_assigned' in action and action['tasks_assigned']:
            task_data = action['tasks_assigned']
            if isinstance(task_data, (list, dict)) and task_data:
                score += 0.1  # Bonus for task assignment details
        
        # Check for execution success indicators
        if any(action.get(key) for key in ['success', 'completed', 'executed']):
            score += 0.2  # Bonus for execution confirmation
        
        if actions_taken == 0:
            issues.append("No specific actions recorded")
        
        return min(score, max_score)
    
    def _score_outcome(self, episode: Episode, issues: List[str]) -> float:
        """Score the outcome availability and quality."""
        if not episode.outcome:
            issues.append("Missing outcome data (reduces learning value)")
            return 0.3  # Partial score for episodes without outcomes yet
        
        score = 0.3  # Base score for having any outcome
        max_score = 1.0
        
        outcome = episode.outcome
        
        # Check for outcome components
        if 'success' in outcome:
            score += 0.2  # Success indicator worth 20%
        
        if 'metrics' in outcome and outcome['metrics']:
            score += 0.2  # Metrics data worth 20%
        
        if 'feedback' in outcome and outcome['feedback']:
            score += 0.1  # Feedback worth 10%
        
        # Quality score bonus
        if episode.outcome_quality is not None:
            if episode.outcome_quality >= 0.8:
                score += 0.2  # High quality outcome
            elif episode.outcome_quality >= 0.6:
                score += 0.1  # Medium quality outcome
        else:
            issues.append("No outcome quality score available")
        
        return min(score, max_score)
    
    def get_quality_report(self, episode: Episode) -> Dict[str, Any]:
        """
        Generate detailed quality report for an episode.
        
        Args:
            episode: Episode to analyze
            
        Returns:
            Detailed quality report dictionary
        """
        is_valid, quality_score, issues = self.validate_episode(episode)
        
        # Get component scores
        perception_score = self._score_perception(episode.perception, [])
        reasoning_score = self._score_reasoning(episode.reasoning, [])
        action_score = self._score_action(episode.action, [])
        outcome_score = self._score_outcome(episode, [])
        
        return {
            'episode_id': str(episode.episode_id) if episode.episode_id else None,
            'project_id': episode.project_id,
            'overall_quality': quality_score,
            'is_valid_for_learning': is_valid,
            'quality_threshold': self.quality_threshold,
            'component_scores': {
                'perception': perception_score,
                'reasoning': reasoning_score,
                'action': action_score,
                'outcome': outcome_score
            },
            'issues': issues,
            'recommendations': self._generate_recommendations(issues, quality_score)
        }
    
    def _generate_recommendations(self, issues: List[str], quality_score: float) -> List[str]:
        """Generate recommendations for improving episode quality."""
        recommendations = []
        
        if quality_score < 0.5:
            recommendations.append("Episode quality is below acceptable threshold - review data collection process")
        
        if any("Missing" in issue for issue in issues):
            recommendations.append("Ensure all essential data fields are captured during episode recording")
        
        if any("reasoning" in issue.lower() for issue in issues):
            recommendations.append("Enhance decision reasoning capture to include more analysis details")
        
        if any("outcome" in issue.lower() for issue in issues):
            recommendations.append("Implement outcome tracking for better learning value")
        
        if not recommendations:
            recommendations.append("Episode quality is acceptable for learning purposes")
        
        return recommendations

# Convenience functions for direct use
def validate_episode(episode: Episode, quality_threshold: float = 0.7) -> Tuple[bool, float, List[str]]:
    """Validate a single episode with default validator."""
    validator = EpisodeValidator(quality_threshold)
    return validator.validate_episode(episode)

def get_episode_quality_score(episode: Episode) -> float:
    """Get quality score for an episode."""
    validator = EpisodeValidator()
    _, quality_score, _ = validator.validate_episode(episode)
    return quality_score