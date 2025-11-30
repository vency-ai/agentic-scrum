"""
Pattern Combiner Component

Intelligently combines episode-based patterns with Chronicle Service patterns
to create hybrid intelligence for decision-making. This component weighs 
different pattern sources based on confidence, relevance, and quality.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from statistics import mean, stdev
from dataclasses import dataclass

from model_package.decision_context import DecisionPattern, EpisodeBasedDecisionContext
from models import PatternAnalysis, SimilarProject, SuccessIndicators

logger = logging.getLogger(__name__)

@dataclass
class CombinedPattern:
    """Combined pattern from multiple sources with confidence weighting"""
    pattern_type: str
    pattern_value: Any
    success_rate: float
    confidence: float
    episode_source_weight: float
    chronicle_source_weight: float
    total_evidence_count: int
    source_breakdown: Dict[str, Any]

@dataclass
class PatternCombinationResult:
    """Result of pattern combination process"""
    combined_patterns: List[CombinedPattern]
    overall_confidence: float
    pattern_source_influence: Dict[str, float]
    reasoning: List[str]
    metadata: Dict[str, Any]

class PatternCombiner:
    """Combines episode patterns with Chronicle patterns intelligently"""
    
    def __init__(self, 
                 episode_weight_base: float = 0.4,
                 chronicle_weight_base: float = 0.6,
                 min_confidence_threshold: float = 0.3):
        """
        Initialize Pattern Combiner.
        
        Args:
            episode_weight_base: Base weight for episode patterns
            chronicle_weight_base: Base weight for Chronicle patterns
            min_confidence_threshold: Minimum confidence to consider pattern
        """
        self.episode_weight_base = episode_weight_base
        self.chronicle_weight_base = chronicle_weight_base
        self.min_confidence_threshold = min_confidence_threshold
        
    def combine_patterns(
        self,
        episode_context: Optional[EpisodeBasedDecisionContext],
        chronicle_analysis: Optional[PatternAnalysis],
        current_project_context: Dict[str, Any]
    ) -> PatternCombinationResult:
        """
        Combine patterns from episode memory and Chronicle Service.
        
        Args:
            episode_context: Episode-based decision context from Memory Bridge
            chronicle_analysis: Pattern analysis from Chronicle Service  
            current_project_context: Current project context for relevance weighting
            
        Returns:
            Combined pattern analysis with hybrid intelligence
        """
        start_time = logger.info("Starting pattern combination")
        
        try:
            combined_patterns = []
            reasoning = []
            pattern_source_influence = {"episode": 0.0, "chronicle": 0.0}
            
            # Calculate dynamic source weights based on data quality
            episode_weight, chronicle_weight = self._calculate_source_weights(
                episode_context, chronicle_analysis
            )
            
            pattern_source_influence["episode"] = episode_weight
            pattern_source_influence["chronicle"] = chronicle_weight
            
            # Combine task count patterns
            task_patterns = self._combine_task_count_patterns(
                episode_context, chronicle_analysis, episode_weight, chronicle_weight
            )
            combined_patterns.extend(task_patterns['patterns'])
            reasoning.extend(task_patterns['reasoning'])
            
            # Combine sprint duration patterns  
            duration_patterns = self._combine_sprint_duration_patterns(
                episode_context, chronicle_analysis, episode_weight, chronicle_weight
            )
            combined_patterns.extend(duration_patterns['patterns'])
            reasoning.extend(duration_patterns['reasoning'])
            
            # Calculate overall confidence
            overall_confidence = self._calculate_overall_confidence(
                combined_patterns, episode_context, chronicle_analysis
            )
            
            # Add combination metadata
            metadata = {
                "episode_episodes_count": episode_context.episodes_used_for_context if episode_context else 0,
                "chronicle_projects_count": len(chronicle_analysis.similar_projects) if chronicle_analysis else 0,
                "combination_strategy": "confidence_weighted_average",
                "source_weights": {"episode": episode_weight, "chronicle": chronicle_weight}
            }
            
            result = PatternCombinationResult(
                combined_patterns=combined_patterns,
                overall_confidence=overall_confidence,
                pattern_source_influence=pattern_source_influence,
                reasoning=reasoning,
                metadata=metadata
            )
            
            logger.info(f"Pattern combination complete: {len(combined_patterns)} patterns, "
                       f"confidence: {overall_confidence:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Pattern combination failed: {e}")
            # Return empty result on failure
            return PatternCombinationResult(
                combined_patterns=[],
                overall_confidence=0.0,
                pattern_source_influence={"episode": 0.0, "chronicle": 0.0},
                reasoning=["Pattern combination failed due to error"],
                metadata={"error": str(e)}
            )
    
    def _calculate_source_weights(
        self, 
        episode_context: Optional[EpisodeBasedDecisionContext],
        chronicle_analysis: Optional[PatternAnalysis]
    ) -> Tuple[float, float]:
        """Calculate dynamic weights for episode vs Chronicle patterns based on data quality"""
        
        episode_quality_score = 0.0
        chronicle_quality_score = 0.0
        
        # Evaluate episode context quality
        if episode_context:
            # Base quality on episode count, similarity, and confidence
            episode_count_score = min(episode_context.episodes_used_for_context / 5, 1.0)
            similarity_score = episode_context.average_episode_similarity
            confidence_score = episode_context.overall_recommendation_confidence
            
            episode_quality_score = (episode_count_score * 0.3 + 
                                   similarity_score * 0.4 + 
                                   confidence_score * 0.3)
        
        # Evaluate Chronicle analysis quality
        if chronicle_analysis:
            # Base quality on similar project count and confidence
            project_count_score = min(len(chronicle_analysis.similar_projects) / 10, 1.0)
            
            # Calculate average similarity from Chronicle projects
            if chronicle_analysis.similar_projects:
                avg_chronicle_similarity = mean([p.similarity_score for p in chronicle_analysis.similar_projects])
            else:
                avg_chronicle_similarity = 0.0
                
            chronicle_quality_score = (project_count_score * 0.5 + avg_chronicle_similarity * 0.5)
        
        # Normalize weights based on quality scores
        total_quality = episode_quality_score + chronicle_quality_score
        
        if total_quality > 0:
            # Dynamic weighting based on quality
            episode_weight = (episode_quality_score / total_quality) * 0.8 + 0.1  # Min 10%
            chronicle_weight = (chronicle_quality_score / total_quality) * 0.8 + 0.1  # Min 10%
        else:
            # Fallback to base weights if no quality data
            episode_weight = self.episode_weight_base
            chronicle_weight = self.chronicle_weight_base
        
        # Ensure weights sum to 1.0
        total_weight = episode_weight + chronicle_weight
        episode_weight = episode_weight / total_weight
        chronicle_weight = chronicle_weight / total_weight
        
        logger.debug(f"Source weights calculated: episode={episode_weight:.2f}, "
                    f"chronicle={chronicle_weight:.2f}")
        
        return episode_weight, chronicle_weight
    
    def _combine_task_count_patterns(
        self,
        episode_context: Optional[EpisodeBasedDecisionContext],
        chronicle_analysis: Optional[PatternAnalysis],
        episode_weight: float,
        chronicle_weight: float
    ) -> Dict[str, List]:
        """Combine task count patterns from both sources"""
        
        patterns = []
        reasoning = []
        
        episode_task_pattern = None
        chronicle_task_pattern = None
        
        # Extract episode task count pattern
        if episode_context and episode_context.identified_patterns:
            episode_task_patterns = [p for p in episode_context.identified_patterns 
                                   if p.pattern_type == "task_count"]
            if episode_task_patterns:
                # Use the highest confidence pattern
                episode_task_pattern = max(episode_task_patterns, key=lambda p: p.confidence)
        
        # Extract Chronicle task count pattern  
        if chronicle_analysis and chronicle_analysis.success_indicators:
            chronicle_task_pattern = {
                "pattern_value": chronicle_analysis.success_indicators.optimal_tasks_per_sprint,
                "success_rate": chronicle_analysis.success_indicators.success_probability,
                "confidence": chronicle_analysis.success_indicators.success_probability,  # Use success prob as confidence
                "evidence_count": len(chronicle_analysis.similar_projects)
            }
        
        # Combine patterns if both sources available
        if episode_task_pattern and chronicle_task_pattern:
            # Weighted average of recommendations
            episode_tasks = episode_task_pattern.pattern_value
            chronicle_tasks = chronicle_task_pattern["pattern_value"]
            
            weighted_tasks = (episode_tasks * episode_weight + 
                            chronicle_tasks * chronicle_weight)
            
            # Weighted average of success rates
            weighted_success_rate = (episode_task_pattern.success_rate * episode_weight +
                                   chronicle_task_pattern["success_rate"] * chronicle_weight)
            
            # Combined confidence
            combined_confidence = (episode_task_pattern.confidence * episode_weight +
                                 chronicle_task_pattern["confidence"] * chronicle_weight)
            
            combined_pattern = CombinedPattern(
                pattern_type="task_count",
                pattern_value=round(weighted_tasks),
                success_rate=weighted_success_rate,
                confidence=combined_confidence,
                episode_source_weight=episode_weight,
                chronicle_source_weight=chronicle_weight,
                total_evidence_count=(episode_task_pattern.episode_count + 
                                    chronicle_task_pattern["evidence_count"]),
                source_breakdown={
                    "episode": {
                        "value": episode_tasks,
                        "success_rate": episode_task_pattern.success_rate,
                        "confidence": episode_task_pattern.confidence,
                        "evidence": episode_task_pattern.episode_count
                    },
                    "chronicle": {
                        "value": chronicle_tasks,
                        "success_rate": chronicle_task_pattern["success_rate"], 
                        "confidence": chronicle_task_pattern["confidence"],
                        "evidence": chronicle_task_pattern["evidence_count"]
                    }
                }
            )
            
            patterns.append(combined_pattern)
            reasoning.append(f"Combined task count: episode suggests {episode_tasks} tasks "
                           f"({episode_task_pattern.success_rate:.1%} success), Chronicle suggests "
                           f"{chronicle_tasks} tasks ({chronicle_task_pattern['success_rate']:.1%} success). "
                           f"Weighted recommendation: {round(weighted_tasks)} tasks")
            
        elif episode_task_pattern:
            # Episode-only pattern
            combined_pattern = CombinedPattern(
                pattern_type="task_count",
                pattern_value=episode_task_pattern.pattern_value,
                success_rate=episode_task_pattern.success_rate,
                confidence=episode_task_pattern.confidence * 0.8,  # Reduce confidence for single source
                episode_source_weight=1.0,
                chronicle_source_weight=0.0,
                total_evidence_count=episode_task_pattern.episode_count,
                source_breakdown={"episode_only": True}
            )
            patterns.append(combined_pattern)
            reasoning.append(f"Episode-based task count: {episode_task_pattern.pattern_value} tasks "
                           f"(no Chronicle data available)")
            
        elif chronicle_task_pattern:
            # Chronicle-only pattern
            combined_pattern = CombinedPattern(
                pattern_type="task_count", 
                pattern_value=chronicle_task_pattern["pattern_value"],
                success_rate=chronicle_task_pattern["success_rate"],
                confidence=chronicle_task_pattern["confidence"] * 0.8,  # Reduce confidence for single source
                episode_source_weight=0.0,
                chronicle_source_weight=1.0,
                total_evidence_count=chronicle_task_pattern["evidence_count"],
                source_breakdown={"chronicle_only": True}
            )
            patterns.append(combined_pattern)
            reasoning.append(f"Chronicle-based task count: {chronicle_task_pattern['pattern_value']} tasks "
                           f"(no episode data available)")
        
        return {"patterns": patterns, "reasoning": reasoning}
    
    def _combine_sprint_duration_patterns(
        self,
        episode_context: Optional[EpisodeBasedDecisionContext],
        chronicle_analysis: Optional[PatternAnalysis],
        episode_weight: float,
        chronicle_weight: float
    ) -> Dict[str, List]:
        """Combine sprint duration patterns from both sources"""
        
        patterns = []
        reasoning = []
        
        episode_duration_pattern = None
        chronicle_duration_pattern = None
        
        # Extract episode sprint duration pattern
        if episode_context and episode_context.identified_patterns:
            episode_duration_patterns = [p for p in episode_context.identified_patterns 
                                       if p.pattern_type == "sprint_duration"]
            if episode_duration_patterns:
                episode_duration_pattern = max(episode_duration_patterns, key=lambda p: p.confidence)
        
        # Extract Chronicle sprint duration pattern
        if chronicle_analysis and chronicle_analysis.success_indicators:
            chronicle_duration_pattern = {
                "pattern_value": chronicle_analysis.success_indicators.recommended_sprint_duration,
                "success_rate": chronicle_analysis.success_indicators.success_probability,
                "confidence": chronicle_analysis.success_indicators.success_probability,
                "evidence_count": len(chronicle_analysis.similar_projects)
            }
        
        # Combine patterns if both sources available
        if episode_duration_pattern and chronicle_duration_pattern:
            # For duration, use the higher confidence recommendation
            if episode_duration_pattern.confidence >= chronicle_duration_pattern["confidence"]:
                selected_duration = episode_duration_pattern.pattern_value
                primary_source = "episode"
            else:
                selected_duration = chronicle_duration_pattern["pattern_value"]
                primary_source = "chronicle"
            
            # Combined confidence based on agreement
            if episode_duration_pattern.pattern_value == chronicle_duration_pattern["pattern_value"]:
                # Same recommendation - boost confidence
                combined_confidence = min(episode_duration_pattern.confidence + 
                                        chronicle_duration_pattern["confidence"], 1.0)
                agreement = "both sources agree"
            else:
                # Different recommendations - average confidence
                combined_confidence = (episode_duration_pattern.confidence * episode_weight +
                                     chronicle_duration_pattern["confidence"] * chronicle_weight)
                agreement = "sources disagree, using higher confidence"
            
            combined_pattern = CombinedPattern(
                pattern_type="sprint_duration",
                pattern_value=selected_duration,
                success_rate=(episode_duration_pattern.success_rate * episode_weight +
                            chronicle_duration_pattern["success_rate"] * chronicle_weight),
                confidence=combined_confidence,
                episode_source_weight=episode_weight,
                chronicle_source_weight=chronicle_weight,
                total_evidence_count=(episode_duration_pattern.episode_count +
                                    chronicle_duration_pattern["evidence_count"]),
                source_breakdown={
                    "primary_source": primary_source,
                    "agreement": agreement,
                    "episode": episode_duration_pattern.pattern_value,
                    "chronicle": chronicle_duration_pattern["pattern_value"]
                }
            )
            
            patterns.append(combined_pattern)
            reasoning.append(f"Combined sprint duration: {selected_duration} weeks "
                           f"({agreement}, confidence: {combined_confidence:.1%})")
            
        elif episode_duration_pattern:
            # Episode-only pattern
            combined_pattern = CombinedPattern(
                pattern_type="sprint_duration",
                pattern_value=episode_duration_pattern.pattern_value,
                success_rate=episode_duration_pattern.success_rate,
                confidence=episode_duration_pattern.confidence * 0.8,
                episode_source_weight=1.0,
                chronicle_source_weight=0.0,
                total_evidence_count=episode_duration_pattern.episode_count,
                source_breakdown={"episode_only": True}
            )
            patterns.append(combined_pattern)
            reasoning.append(f"Episode-based sprint duration: {episode_duration_pattern.pattern_value} weeks")
            
        elif chronicle_duration_pattern:
            # Chronicle-only pattern
            combined_pattern = CombinedPattern(
                pattern_type="sprint_duration",
                pattern_value=chronicle_duration_pattern["pattern_value"],
                success_rate=chronicle_duration_pattern["success_rate"], 
                confidence=chronicle_duration_pattern["confidence"] * 0.8,
                episode_source_weight=0.0,
                chronicle_source_weight=1.0,
                total_evidence_count=chronicle_duration_pattern["evidence_count"],
                source_breakdown={"chronicle_only": True}
            )
            patterns.append(combined_pattern)
            reasoning.append(f"Chronicle-based sprint duration: {chronicle_duration_pattern['pattern_value']} weeks")
        
        return {"patterns": patterns, "reasoning": reasoning}
    
    def _calculate_overall_confidence(
        self,
        combined_patterns: List[CombinedPattern],
        episode_context: Optional[EpisodeBasedDecisionContext],
        chronicle_analysis: Optional[PatternAnalysis]
    ) -> float:
        """Calculate overall confidence in the combined patterns"""
        
        if not combined_patterns:
            return 0.0
        
        # Base confidence on pattern confidences
        pattern_confidences = [p.confidence for p in combined_patterns]
        base_confidence = mean(pattern_confidences)
        
        # Adjust based on data availability
        data_availability_score = 0.0
        
        if episode_context and episode_context.episodes_used_for_context > 0:
            data_availability_score += 0.4
        
        if chronicle_analysis and chronicle_analysis.similar_projects:
            data_availability_score += 0.4
            
        # Bonus for having both sources
        if (episode_context and episode_context.episodes_used_for_context > 0 and
            chronicle_analysis and chronicle_analysis.similar_projects):
            data_availability_score += 0.2
        
        # Combined confidence
        overall_confidence = base_confidence * data_availability_score
        
        return min(overall_confidence, 1.0)
    
    def get_recommended_values(self, combination_result: PatternCombinationResult) -> Dict[str, Any]:
        """Extract recommended values from combined patterns"""
        
        recommendations = {}
        
        for pattern in combination_result.combined_patterns:
            if pattern.confidence >= self.min_confidence_threshold:
                if pattern.pattern_type == "task_count":
                    recommendations["recommended_task_count"] = pattern.pattern_value
                elif pattern.pattern_type == "sprint_duration":
                    recommendations["recommended_sprint_duration_weeks"] = pattern.pattern_value
        
        return recommendations