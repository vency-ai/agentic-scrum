"""
Memory Bridge Service

Translates raw episode data from the Episode Retriever into structured
decision context that can be consumed by the Enhanced Decision Engine.
"""

import logging
import time
from typing import List, Dict, Any, Optional
from uuid import UUID
from statistics import mean, stdev

from memory.models import Episode
from model_package.decision_context import (
    EpisodeBasedDecisionContext,
    EpisodeInsight,
    DecisionPattern,
    EpisodeInfluenceMetadata
)
from analytics.episode_pattern_analyzer import EpisodePatternAnalyzer

logger = logging.getLogger(__name__)

class MemoryBridge:
    """Bridges episode data to decision context"""
    
    def __init__(self, 
                 min_episodes_for_patterns: int = 2,
                 min_similarity_threshold: float = 0.6,
                 quality_weight: float = 0.3):
        """
        Initialize Memory Bridge.
        
        Args:
            min_episodes_for_patterns: Minimum episodes needed to identify patterns
            min_similarity_threshold: Minimum similarity to consider episode relevant
            quality_weight: Weight for episode quality in confidence calculations
        """
        self.min_episodes_for_patterns = min_episodes_for_patterns
        self.min_similarity_threshold = min_similarity_threshold
        self.quality_weight = quality_weight
        
        # Initialize Episode Pattern Analyzer
        self.pattern_analyzer = EpisodePatternAnalyzer(
            min_pattern_support=min_episodes_for_patterns,
            min_confidence_threshold=0.5,
            success_threshold=0.7
        )
        
    async def translate_episodes_to_context(
        self, 
        episodes: List[Episode], 
        current_project_context: Dict[str, Any]
    ) -> EpisodeBasedDecisionContext:
        """
        Translate episode data into structured decision context.
        
        Args:
            episodes: List of similar episodes from Episode Retriever
            current_project_context: Current project context for comparison
            
        Returns:
            Structured decision context for Enhanced Decision Engine
        """
        start_time = time.time()
        
        try:
            # Filter episodes by similarity and quality
            relevant_episodes = self._filter_relevant_episodes(episodes)
            
            if not relevant_episodes:
                return self._create_empty_context(processing_duration_ms=(time.time() - start_time) * 1000)
            
            # Extract insights from individual episodes
            episode_insights = self._extract_episode_insights(relevant_episodes, current_project_context)
            
            # Identify patterns across episodes using both Memory Bridge and Episode Pattern Analyzer
            memory_bridge_patterns = self._identify_decision_patterns(relevant_episodes, current_project_context)
            
            # Use Episode Pattern Analyzer for advanced pattern detection
            advanced_patterns, pattern_insights = self.pattern_analyzer.analyze_patterns(
                relevant_episodes, 
                current_project_context
            )
            
            # Combine patterns from both sources
            decision_patterns = memory_bridge_patterns + advanced_patterns
            
            # Calculate success metrics
            success_metrics = self._calculate_success_metrics(relevant_episodes)
            
            # Generate recommendations
            recommendations = self._generate_recommendations(decision_patterns, success_metrics)
            
            # Create key insights (human readable) - combine Memory Bridge insights with Pattern Analyzer insights
            memory_bridge_insights = self._generate_key_insights(
                relevant_episodes, 
                decision_patterns, 
                success_metrics,
                current_project_context
            )
            
            # Merge insights from Episode Pattern Analyzer
            all_insights = memory_bridge_insights['insights'] + [insight.insight_text for insight in pattern_insights]
            
            key_insights = {
                'insights': all_insights,
                'success_factors': memory_bridge_insights['success_factors'],
                'risk_factors': memory_bridge_insights['risk_factors']
            }
            
            # Calculate overall confidence
            overall_confidence = self._calculate_overall_confidence(
                relevant_episodes, 
                decision_patterns, 
                success_metrics
            )
            
            # Build context
            context = EpisodeBasedDecisionContext(
                similar_episodes_analyzed=len(episodes),
                episodes_used_for_context=len(relevant_episodes),
                average_episode_similarity=mean([ep.similarity for ep in relevant_episodes]) if relevant_episodes else 0.0,
                context_quality_score=self._calculate_context_quality(relevant_episodes),
                
                average_success_rate=success_metrics.get('average_success_rate'),
                success_rate_confidence=success_metrics.get('confidence', 0.0),
                
                identified_patterns=decision_patterns,
                
                recommended_task_count=recommendations.get('task_count'),
                recommended_sprint_duration_weeks=recommendations.get('sprint_duration_weeks'),
                recommended_team_assignments=recommendations.get('team_assignments'),
                
                overall_recommendation_confidence=overall_confidence,
                pattern_confidence_weight=self._calculate_pattern_weight(relevant_episodes),
                
                key_insights=key_insights['insights'],
                success_factors=key_insights['success_factors'],
                risk_factors=key_insights['risk_factors'],
                
                contributing_episodes=episode_insights,
                
                processing_duration_ms=(time.time() - start_time) * 1000
            )
            
            logger.info(f"Memory Bridge translated {len(episodes)} episodes into decision context "
                       f"({len(relevant_episodes)} relevant, confidence: {overall_confidence:.2f})")
            
            return context
            
        except Exception as e:
            logger.error(f"Memory Bridge translation failed: {e}")
            return self._create_empty_context(processing_duration_ms=(time.time() - start_time) * 1000)
    
    def _filter_relevant_episodes(self, episodes: List[Episode]) -> List[Episode]:
        """Filter episodes by similarity and quality thresholds"""
        relevant = []
        
        for episode in episodes:
            # Check similarity threshold
            if hasattr(episode, 'similarity') and episode.similarity < self.min_similarity_threshold:
                continue
                
            # Check quality threshold (if available)
            if episode.outcome_quality is not None and episode.outcome_quality < 0.5:
                continue
                
            # Check data completeness
            if not self._is_episode_complete(episode):
                continue
                
            relevant.append(episode)
        
        logger.debug(f"Filtered {len(episodes)} episodes to {len(relevant)} relevant episodes")
        return relevant
    
    def _is_episode_complete(self, episode: Episode) -> bool:
        """Check if episode has sufficient data for analysis"""
        try:
            # Must have basic decision data
            action = episode.action if isinstance(episode.action, dict) else {}
            reasoning = episode.reasoning if isinstance(episode.reasoning, dict) else {}
            
            if not action or not reasoning:
                return False
                
            # Must have project context
            perception = episode.perception if isinstance(episode.perception, dict) else {}
            if not perception:
                return False
                
            # Check for key context fields
            if not perception.get('team_size'):
                return False
                
            return True
        except Exception:
            return False
    
    def _extract_episode_insights(
        self, 
        episodes: List[Episode], 
        current_context: Dict[str, Any]
    ) -> List[EpisodeInsight]:
        """Extract insights from individual episodes"""
        insights = []
        
        for episode in episodes:
            try:
                # Handle episode_id conversion properly
                episode_id = episode.episode_id
                if isinstance(episode_id, str):
                    episode_id = UUID(episode_id)
                elif not isinstance(episode_id, UUID):
                    episode_id = UUID(str(episode_id))
                
                insight = EpisodeInsight(
                    episode_id=episode_id,
                    project_id=episode.project_id,
                    similarity_score=getattr(episode, 'similarity', 0.0),
                    outcome_quality=episode.outcome_quality,
                    decision_summary=self._summarize_episode_decision(episode),
                    key_learning=self._extract_key_learning(episode, current_context),
                    confidence=self._calculate_episode_confidence(episode)
                )
                insights.append(insight)
            except Exception as e:
                logger.warning(f"Failed to extract insight from episode {episode.episode_id}: {e}")
                
        return insights
    
    def _summarize_episode_decision(self, episode: Episode) -> str:
        """Create human-readable summary of episode decision"""
        try:
            action = episode.action if isinstance(episode.action, dict) else {}
            
            # Extract key decision points
            decisions = []
            
            if action.get('create_new_sprint'):
                task_count = action.get('tasks_to_assign', 'unknown')
                decisions.append(f"Created sprint with {task_count} tasks")
                
            if action.get('sprint_duration_weeks'):
                decisions.append(f"{action['sprint_duration_weeks']}-week sprint")
                
            if decisions:
                summary = ", ".join(decisions)
                
                # Add outcome if available
                if episode.outcome_quality and episode.outcome_quality > 0.8:
                    summary += ", completed successfully"
                elif episode.outcome_quality and episode.outcome_quality < 0.6:
                    summary += ", encountered challenges"
                    
                return summary
                
            return f"Decision made for project {episode.project_id}"
            
        except Exception as e:
            logger.warning(f"Failed to summarize episode decision: {e}")
            return f"Decision for project {episode.project_id}"
    
    def _extract_key_learning(self, episode: Episode, current_context: Dict[str, Any]) -> str:
        """Extract key learning from episode relevant to current context"""
        try:
            perception = episode.perception if isinstance(episode.perception, dict) else {}
            action = episode.action if isinstance(episode.action, dict) else {}
            
            current_team_size = current_context.get('team_size', 0)
            episode_team_size = perception.get('team_size', 0)
            
            # Generate contextual learning
            if abs(current_team_size - episode_team_size) <= 1:  # Similar team size
                task_count = action.get('tasks_to_assign')
                outcome_quality = episode.outcome_quality or 0.5
                
                if task_count and outcome_quality > 0.7:
                    return f"Team size {episode_team_size} handled {task_count} tasks with {outcome_quality:.0%} success"
                elif task_count and outcome_quality < 0.6:
                    return f"Team size {episode_team_size} struggled with {task_count} tasks ({outcome_quality:.0%} success)"
                    
            return f"Similar project context achieved {episode.outcome_quality:.0%} success" if episode.outcome_quality else "Similar project experience"
            
        except Exception:
            return "Historical project experience"
    
    def _identify_decision_patterns(
        self, 
        episodes: List[Episode], 
        current_context: Dict[str, Any]
    ) -> List[DecisionPattern]:
        """Identify patterns across multiple episodes"""
        patterns = []
        
        if len(episodes) < self.min_episodes_for_patterns:
            return patterns
            
        try:
            # Task count patterns
            task_pattern = self._analyze_task_count_pattern(episodes, current_context)
            if task_pattern:
                patterns.append(task_pattern)
                
            # Sprint duration patterns
            duration_pattern = self._analyze_sprint_duration_pattern(episodes, current_context)
            if duration_pattern:
                patterns.append(duration_pattern)
                
            logger.debug(f"Identified {len(patterns)} patterns from {len(episodes)} episodes")
            
        except Exception as e:
            logger.warning(f"Pattern identification failed: {e}")
            
        return patterns
    
    def _analyze_task_count_pattern(self, episodes: List[Episode], current_context: Dict[str, Any]) -> Optional[DecisionPattern]:
        """Analyze task count patterns"""
        try:
            task_counts = []
            outcomes = []
            
            for episode in episodes:
                action = episode.action if isinstance(episode.action, dict) else {}
                task_count = action.get('tasks_to_assign')
                
                if task_count and episode.outcome_quality is not None:
                    task_counts.append(task_count)
                    outcomes.append(episode.outcome_quality)
            
            if len(task_counts) < 2:
                return None
                
            # Find optimal task count
            best_idx = outcomes.index(max(outcomes))
            optimal_task_count = task_counts[best_idx]
            
            # Calculate success rate for this task count
            similar_counts = [tc for tc in task_counts if abs(tc - optimal_task_count) <= 1]
            similar_outcomes = [outcomes[i] for i, tc in enumerate(task_counts) if abs(tc - optimal_task_count) <= 1]
            
            success_rate = mean(similar_outcomes) if similar_outcomes else 0.0
            confidence = min(len(similar_counts) / len(task_counts), 1.0)
            
            return DecisionPattern(
                pattern_type="task_count",
                pattern_value=optimal_task_count,
                success_rate=success_rate,
                episode_count=len(similar_counts),
                confidence=confidence
            )
            
        except Exception as e:
            logger.warning(f"Task count pattern analysis failed: {e}")
            return None
    
    def _analyze_sprint_duration_pattern(self, episodes: List[Episode], current_context: Dict[str, Any]) -> Optional[DecisionPattern]:
        """Analyze sprint duration patterns"""
        try:
            durations = []
            outcomes = []
            
            for episode in episodes:
                action = episode.action if isinstance(episode.action, dict) else {}
                duration = action.get('sprint_duration_weeks')
                
                if duration and episode.outcome_quality is not None:
                    durations.append(duration)
                    outcomes.append(episode.outcome_quality)
            
            if len(durations) < 2:
                return None
                
            # Find most common successful duration
            duration_success = {}
            for duration, outcome in zip(durations, outcomes):
                if duration not in duration_success:
                    duration_success[duration] = []
                duration_success[duration].append(outcome)
            
            # Calculate average success for each duration
            best_duration = None
            best_success_rate = 0
            
            for duration, outcome_list in duration_success.items():
                avg_success = mean(outcome_list)
                if avg_success > best_success_rate:
                    best_success_rate = avg_success
                    best_duration = duration
            
            if best_duration is None:
                return None
                
            confidence = min(len(duration_success[best_duration]) / len(durations), 1.0)
            
            return DecisionPattern(
                pattern_type="sprint_duration",
                pattern_value=best_duration,
                success_rate=best_success_rate,
                episode_count=len(duration_success[best_duration]),
                confidence=confidence
            )
            
        except Exception as e:
            logger.warning(f"Sprint duration pattern analysis failed: {e}")
            return None
    
    def _calculate_success_metrics(self, episodes: List[Episode]) -> Dict[str, Any]:
        """Calculate success metrics from episodes"""
        try:
            outcomes = [ep.outcome_quality for ep in episodes if ep.outcome_quality is not None]
            
            if not outcomes:
                return {'average_success_rate': None, 'confidence': 0.0}
                
            avg_success = mean(outcomes)
            confidence = min(len(outcomes) / max(len(episodes), 1), 1.0)
            
            # Adjust confidence based on outcome variance
            if len(outcomes) > 1:
                outcome_std = stdev(outcomes)
                confidence *= max(0.5, 1.0 - outcome_std)  # Lower confidence for high variance
            
            return {
                'average_success_rate': avg_success,
                'confidence': confidence,
                'outcome_count': len(outcomes)
            }
            
        except Exception as e:
            logger.warning(f"Success metrics calculation failed: {e}")
            return {'average_success_rate': None, 'confidence': 0.0}
    
    def _generate_recommendations(self, patterns: List[DecisionPattern], success_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Generate specific recommendations from patterns"""
        recommendations = {}
        
        for pattern in patterns:
            if pattern.pattern_type == "task_count" and pattern.confidence > 0.5:
                recommendations['task_count'] = pattern.pattern_value
            elif pattern.pattern_type == "sprint_duration" and pattern.confidence > 0.5:
                recommendations['sprint_duration_weeks'] = pattern.pattern_value
                
        return recommendations
    
    def _generate_key_insights(
        self, 
        episodes: List[Episode], 
        patterns: List[DecisionPattern], 
        success_metrics: Dict[str, Any],
        current_context: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """Generate human-readable insights"""
        insights = {
            'insights': [],
            'success_factors': [],
            'risk_factors': []
        }
        
        try:
            # Success rate insights
            if success_metrics.get('average_success_rate'):
                success_rate = success_metrics['average_success_rate']
                episode_count = len(episodes)
                insights['insights'].append(
                    f"Similar projects achieved {success_rate:.0%} success rate across {episode_count} episodes"
                )
                
            # Pattern-based insights
            for pattern in patterns:
                if pattern.pattern_type == "task_count" and pattern.confidence > 0.6:
                    insights['insights'].append(
                        f"Optimal task count appears to be {pattern.pattern_value} "
                        f"({pattern.success_rate:.0%} success rate, {pattern.episode_count} episodes)"
                    )
                    insights['success_factors'].append(f"Task count around {pattern.pattern_value}")
                    
                elif pattern.pattern_type == "sprint_duration" and pattern.confidence > 0.6:
                    insights['insights'].append(
                        f"{pattern.pattern_value}-week sprints showed {pattern.success_rate:.0%} success rate"
                    )
                    insights['success_factors'].append(f"{pattern.pattern_value}-week sprint duration")
            
            # Risk factors based on low-performing episodes
            low_performers = [ep for ep in episodes if ep.outcome_quality and ep.outcome_quality < 0.6]
            if low_performers:
                insights['risk_factors'].append(
                    f"{len(low_performers)} similar episodes had challenges - review their contexts"
                )
                
        except Exception as e:
            logger.warning(f"Key insights generation failed: {e}")
            
        return insights
    
    def _calculate_overall_confidence(
        self, 
        episodes: List[Episode], 
        patterns: List[DecisionPattern], 
        success_metrics: Dict[str, Any]
    ) -> float:
        """Calculate overall confidence in the decision context"""
        try:
            confidence_factors = []
            
            # Episode quantity confidence
            quantity_confidence = min(len(episodes) / 5, 1.0)  # Max at 5 episodes
            confidence_factors.append(quantity_confidence)
            
            # Episode quality confidence
            quality_scores = [ep.outcome_quality for ep in episodes if ep.outcome_quality is not None]
            if quality_scores:
                quality_confidence = mean(quality_scores)
                confidence_factors.append(quality_confidence)
            
            # Pattern confidence
            if patterns:
                pattern_confidences = [p.confidence for p in patterns]
                avg_pattern_confidence = mean(pattern_confidences)
                confidence_factors.append(avg_pattern_confidence)
            
            # Success metrics confidence
            success_confidence = success_metrics.get('confidence', 0.0)
            confidence_factors.append(success_confidence)
            
            # Calculate weighted average
            if confidence_factors:
                return mean(confidence_factors)
            else:
                return 0.0
                
        except Exception:
            return 0.0
    
    def _calculate_context_quality(self, episodes: List[Episode]) -> float:
        """Calculate quality of the decision context"""
        try:
            if not episodes:
                return 0.0
                
            # Quality factors
            complete_episodes = sum(1 for ep in episodes if self._is_episode_complete(ep))
            completeness_score = complete_episodes / len(episodes)
            
            # Similarity distribution (prefer diverse but relevant episodes)
            similarities = [getattr(ep, 'similarity', 0.0) for ep in episodes]
            avg_similarity = mean(similarities) if similarities else 0.0
            
            # Combined quality score
            quality = (completeness_score * 0.7) + (avg_similarity * 0.3)
            return min(quality, 1.0)
            
        except Exception:
            return 0.0
    
    def _calculate_pattern_weight(self, episodes: List[Episode]) -> float:
        """Calculate weight to give episode patterns vs Chronicle patterns"""
        try:
            if not episodes:
                return 0.0
                
            # Base weight on episode count and quality
            base_weight = min(len(episodes) / 5, 1.0)  # Max at 5 episodes
            
            # Adjust for episode quality
            quality_scores = [ep.outcome_quality for ep in episodes if ep.outcome_quality is not None]
            if quality_scores:
                avg_quality = mean(quality_scores)
                quality_weight = avg_quality
            else:
                quality_weight = 0.5  # Default if no quality data
            
            # Combined weight (episode patterns vs Chronicle patterns)
            weight = (base_weight * 0.6) + (quality_weight * 0.4)
            return min(weight, 0.8)  # Cap at 80% to preserve Chronicle influence
            
        except Exception:
            return 0.3  # Default modest weight
    
    def _calculate_episode_confidence(self, episode: Episode) -> float:
        """Calculate confidence in individual episode"""
        try:
            factors = []
            
            # Outcome quality
            if episode.outcome_quality is not None:
                factors.append(episode.outcome_quality)
            
            # Data completeness
            completeness = 1.0 if self._is_episode_complete(episode) else 0.5
            factors.append(completeness)
            
            # Similarity (if available)
            if hasattr(episode, 'similarity'):
                factors.append(episode.similarity)
            
            return mean(factors) if factors else 0.5
            
        except Exception:
            return 0.5
    
    def _create_empty_context(self, processing_duration_ms: float = 0.0) -> EpisodeBasedDecisionContext:
        """Create empty context when no episodes available"""
        return EpisodeBasedDecisionContext(
            similar_episodes_analyzed=0,
            episodes_used_for_context=0,
            average_episode_similarity=0.0,
            context_quality_score=0.0,
            overall_recommendation_confidence=0.0,
            pattern_confidence_weight=0.0,
            processing_duration_ms=processing_duration_ms
        )