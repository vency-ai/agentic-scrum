"""
Episode Pattern Analyzer

Analyzes patterns within sets of similar episodes to extract actionable
insights for decision-making. Identifies common decision patterns,
success rates, and outcome predictions.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict, Counter
from statistics import mean, median, mode, stdev
from dataclasses import dataclass

from memory.models import Episode
from model_package.decision_context import DecisionPattern

logger = logging.getLogger(__name__)

@dataclass
class PatternInsight:
    """Insight derived from pattern analysis"""
    pattern_type: str
    insight_text: str
    confidence: float
    supporting_episodes: int
    success_correlation: Optional[float] = None

class EpisodePatternAnalyzer:
    """Analyzes patterns across sets of episodes"""
    
    def __init__(self, 
                 min_pattern_support: int = 2,
                 min_confidence_threshold: float = 0.5,
                 success_threshold: float = 0.7):
        """
        Initialize pattern analyzer.
        
        Args:
            min_pattern_support: Minimum episodes needed to establish pattern
            min_confidence_threshold: Minimum confidence for pattern validity
            success_threshold: Success rate threshold for positive patterns
        """
        self.min_pattern_support = min_pattern_support
        self.min_confidence_threshold = min_confidence_threshold
        self.success_threshold = success_threshold
    
    def analyze_patterns(
        self, 
        episodes: List[Episode], 
        current_context: Dict[str, Any]
    ) -> Tuple[List[DecisionPattern], List[PatternInsight]]:
        """
        Analyze patterns across episodes.
        
        Args:
            episodes: List of similar episodes to analyze
            current_context: Current project context for relevance filtering
            
        Returns:
            Tuple of (decision_patterns, pattern_insights)
        """
        if len(episodes) < self.min_pattern_support:
            logger.debug(f"Insufficient episodes ({len(episodes)}) for pattern analysis")
            return [], []
        
        try:
            decision_patterns = []
            pattern_insights = []
            
            # Analyze task assignment patterns
            task_patterns = self._analyze_task_assignment_patterns(episodes, current_context)
            decision_patterns.extend(task_patterns['patterns'])
            pattern_insights.extend(task_patterns['insights'])
            
            # Analyze sprint duration patterns
            duration_patterns = self._analyze_sprint_duration_patterns(episodes, current_context)
            decision_patterns.extend(duration_patterns['patterns'])
            pattern_insights.extend(duration_patterns['insights'])
            
            # Analyze team size correlation patterns
            team_patterns = self._analyze_team_size_patterns(episodes, current_context)
            decision_patterns.extend(team_patterns['patterns'])
            pattern_insights.extend(team_patterns['insights'])
            
            # Analyze technology stack patterns
            tech_patterns = self._analyze_technology_patterns(episodes, current_context)
            decision_patterns.extend(tech_patterns['patterns'])
            pattern_insights.extend(tech_patterns['insights'])
            
            # Analyze outcome correlation patterns
            outcome_patterns = self._analyze_outcome_correlations(episodes)
            pattern_insights.extend(outcome_patterns['insights'])
            
            logger.info(f"Pattern analysis complete: {len(decision_patterns)} patterns, "
                       f"{len(pattern_insights)} insights from {len(episodes)} episodes")
            
            return decision_patterns, pattern_insights
            
        except Exception as e:
            logger.error(f"Pattern analysis failed: {e}")
            return [], []
    
    def _analyze_task_assignment_patterns(
        self, 
        episodes: List[Episode], 
        current_context: Dict[str, Any]
    ) -> Dict[str, List]:
        """Analyze task assignment patterns"""
        patterns = []
        insights = []
        
        try:
            # Extract task assignment data
            task_data = []
            for episode in episodes:
                action = episode.action if isinstance(episode.action, dict) else {}
                perception = episode.perception if isinstance(episode.perception, dict) else {}
                
                task_count = action.get('tasks_to_assign')
                team_size = perception.get('team_size')
                outcome = episode.outcome_quality
                
                if task_count is not None and team_size is not None and outcome is not None:
                    task_data.append({
                        'task_count': task_count,
                        'team_size': team_size,
                        'outcome': outcome,
                        'ratio': task_count / team_size if team_size > 0 else 0,
                        'episode': episode
                    })
            
            if len(task_data) < self.min_pattern_support:
                return {'patterns': patterns, 'insights': insights}
            
            # Analyze optimal task count
            task_counts = [d['task_count'] for d in task_data]
            outcomes = [d['outcome'] for d in task_data]
            
            # Find task count with best average outcome
            task_outcome_map = defaultdict(list)
            for data in task_data:
                task_outcome_map[data['task_count']].append(data['outcome'])
            
            best_task_count = None
            best_avg_outcome = 0
            
            for task_count, outcome_list in task_outcome_map.items():
                if len(outcome_list) >= self.min_pattern_support:
                    avg_outcome = mean(outcome_list)
                    if avg_outcome > best_avg_outcome and avg_outcome >= self.success_threshold:
                        best_avg_outcome = avg_outcome
                        best_task_count = task_count
            
            if best_task_count is not None:
                supporting_episodes = len(task_outcome_map[best_task_count])
                confidence = min(supporting_episodes / len(task_data), 1.0) * best_avg_outcome
                
                patterns.append(DecisionPattern(
                    pattern_type="task_count",
                    pattern_value=best_task_count,
                    success_rate=best_avg_outcome,
                    episode_count=supporting_episodes,
                    confidence=confidence
                ))
                
                insights.append(PatternInsight(
                    pattern_type="task_assignment",
                    insight_text=f"Task count of {best_task_count} shows {best_avg_outcome:.1%} success rate "
                                f"across {supporting_episodes} similar episodes",
                    confidence=confidence,
                    supporting_episodes=supporting_episodes,
                    success_correlation=best_avg_outcome
                ))
            
            # Analyze task-to-team ratio patterns
            ratios = [d['ratio'] for d in task_data]
            if ratios:
                avg_ratio = mean(ratios)
                current_team_size = current_context.get('team_size', 5)
                suggested_tasks = int(avg_ratio * current_team_size)
                
                insights.append(PatternInsight(
                    pattern_type="task_team_ratio",
                    insight_text=f"Historical task-to-team ratio averages {avg_ratio:.1f}, "
                                f"suggesting ~{suggested_tasks} tasks for team size {current_team_size}",
                    confidence=0.6,
                    supporting_episodes=len(task_data)
                ))
            
        except Exception as e:
            logger.warning(f"Task assignment pattern analysis failed: {e}")
        
        return {'patterns': patterns, 'insights': insights}
    
    def _analyze_sprint_duration_patterns(
        self, 
        episodes: List[Episode], 
        current_context: Dict[str, Any]
    ) -> Dict[str, List]:
        """Analyze sprint duration patterns"""
        patterns = []
        insights = []
        
        try:
            # Extract sprint duration data
            duration_data = []
            for episode in episodes:
                action = episode.action if isinstance(episode.action, dict) else {}
                duration = action.get('sprint_duration_weeks')
                outcome = episode.outcome_quality
                
                if duration is not None and outcome is not None:
                    duration_data.append({
                        'duration': duration,
                        'outcome': outcome,
                        'episode': episode
                    })
            
            if len(duration_data) < self.min_pattern_support:
                return {'patterns': patterns, 'insights': insights}
            
            # Analyze by duration
            duration_outcome_map = defaultdict(list)
            for data in duration_data:
                duration_outcome_map[data['duration']].append(data['outcome'])
            
            # Find best duration
            best_duration = None
            best_avg_outcome = 0
            
            for duration, outcome_list in duration_outcome_map.items():
                if len(outcome_list) >= self.min_pattern_support:
                    avg_outcome = mean(outcome_list)
                    if avg_outcome > best_avg_outcome and avg_outcome >= self.success_threshold:
                        best_avg_outcome = avg_outcome
                        best_duration = duration
            
            if best_duration is not None:
                supporting_episodes = len(duration_outcome_map[best_duration])
                confidence = min(supporting_episodes / len(duration_data), 1.0) * best_avg_outcome
                
                patterns.append(DecisionPattern(
                    pattern_type="sprint_duration",
                    pattern_value=best_duration,
                    success_rate=best_avg_outcome,
                    episode_count=supporting_episodes,
                    confidence=confidence
                ))
                
                insights.append(PatternInsight(
                    pattern_type="sprint_duration",
                    insight_text=f"{best_duration}-week sprints achieve {best_avg_outcome:.1%} success rate "
                                f"in {supporting_episodes} similar projects",
                    confidence=confidence,
                    supporting_episodes=supporting_episodes,
                    success_correlation=best_avg_outcome
                ))
            
        except Exception as e:
            logger.warning(f"Sprint duration pattern analysis failed: {e}")
        
        return {'patterns': patterns, 'insights': insights}
    
    def _analyze_team_size_patterns(
        self, 
        episodes: List[Episode], 
        current_context: Dict[str, Any]
    ) -> Dict[str, List]:
        """Analyze team size correlation patterns"""
        patterns = []
        insights = []
        
        try:
            current_team_size = current_context.get('team_size', 5)
            
            # Group episodes by team size similarity
            team_groups = {
                'similar': [],  # +/- 1 from current
                'smaller': [],  # 2+ smaller
                'larger': []    # 2+ larger
            }
            
            for episode in episodes:
                perception = episode.perception if isinstance(episode.perception, dict) else {}
                team_size = perception.get('team_size')
                
                if team_size is not None and episode.outcome_quality is not None:
                    diff = team_size - current_team_size
                    if abs(diff) <= 1:
                        team_groups['similar'].append(episode)
                    elif diff < -1:
                        team_groups['smaller'].append(episode)
                    elif diff > 1:
                        team_groups['larger'].append(episode)
            
            # Analyze success rates by team size group
            for group_name, group_episodes in team_groups.items():
                if len(group_episodes) >= self.min_pattern_support:
                    outcomes = [ep.outcome_quality for ep in group_episodes]
                    avg_outcome = mean(outcomes)
                    
                    if group_name == 'similar' and avg_outcome >= self.success_threshold:
                        insights.append(PatternInsight(
                            pattern_type="team_size_correlation",
                            insight_text=f"Similar team sizes ({current_team_size}±1) show "
                                        f"{avg_outcome:.1%} success rate in {len(group_episodes)} episodes",
                            confidence=min(len(group_episodes) / len(episodes), 1.0),
                            supporting_episodes=len(group_episodes),
                            success_correlation=avg_outcome
                        ))
                    elif avg_outcome < 0.6:  # Warning for poor performance
                        size_desc = "smaller" if group_name == 'smaller' else "larger"
                        insights.append(PatternInsight(
                            pattern_type="team_size_warning",
                            insight_text=f"{size_desc.title()} teams showed lower success rate "
                                        f"({avg_outcome:.1%}) in {len(group_episodes)} episodes",
                            confidence=0.7,
                            supporting_episodes=len(group_episodes),
                            success_correlation=avg_outcome
                        ))
            
        except Exception as e:
            logger.warning(f"Team size pattern analysis failed: {e}")
        
        return {'patterns': patterns, 'insights': insights}
    
    def _analyze_technology_patterns(
        self, 
        episodes: List[Episode], 
        current_context: Dict[str, Any]
    ) -> Dict[str, List]:
        """Analyze technology stack correlation patterns"""
        patterns = []
        insights = []
        
        try:
            current_tech_stack = set(current_context.get('technology_stack', []))
            
            # Analyze tech stack overlap with outcomes
            tech_overlaps = []
            for episode in episodes:
                perception = episode.perception if isinstance(episode.perception, dict) else {}
                episode_tech = set(perception.get('technology_stack', []))
                
                if episode_tech and episode.outcome_quality is not None:
                    overlap = len(current_tech_stack.intersection(episode_tech))
                    total_unique = len(current_tech_stack.union(episode_tech))
                    similarity = overlap / total_unique if total_unique > 0 else 0
                    
                    tech_overlaps.append({
                        'similarity': similarity,
                        'outcome': episode.outcome_quality,
                        'overlap': overlap,
                        'episode_tech': episode_tech
                    })
            
            if len(tech_overlaps) >= self.min_pattern_support:
                # Analyze correlation between tech similarity and success
                high_similarity = [t for t in tech_overlaps if t['similarity'] > 0.5]
                low_similarity = [t for t in tech_overlaps if t['similarity'] <= 0.5]
                
                if high_similarity and low_similarity:
                    high_avg = mean([t['outcome'] for t in high_similarity])
                    low_avg = mean([t['outcome'] for t in low_similarity])
                    
                    if high_avg > low_avg + 0.1:  # Significant difference
                        insights.append(PatternInsight(
                            pattern_type="technology_correlation",
                            insight_text=f"Projects with similar tech stacks achieve "
                                        f"{high_avg:.1%} vs {low_avg:.1%} success rate",
                            confidence=0.6,
                            supporting_episodes=len(high_similarity),
                            success_correlation=high_avg
                        ))
            
        except Exception as e:
            logger.warning(f"Technology pattern analysis failed: {e}")
        
        return {'patterns': patterns, 'insights': insights}
    
    def _analyze_outcome_correlations(self, episodes: List[Episode]) -> Dict[str, List]:
        """Analyze correlations between various factors and outcomes"""
        insights = []
        
        try:
            # Collect multi-dimensional data
            episode_data = []
            for episode in episodes:
                if episode.outcome_quality is None:
                    continue
                    
                perception = episode.perception if isinstance(episode.perception, dict) else {}
                action = episode.action if isinstance(episode.action, dict) else {}
                
                data = {
                    'outcome': episode.outcome_quality,
                    'team_size': perception.get('team_size'),
                    'backlog_size': perception.get('backlog_tasks'),
                    'task_count': action.get('tasks_to_assign'),
                    'sprint_duration': action.get('sprint_duration_weeks')
                }
                
                # Only include if we have sufficient data
                if sum(1 for v in data.values() if v is not None) >= 3:
                    episode_data.append(data)
            
            if len(episode_data) >= self.min_pattern_support:
                # Analyze backlog size correlation
                backlog_data = [(d['backlog_size'], d['outcome']) for d in episode_data 
                              if d['backlog_size'] is not None]
                
                if len(backlog_data) >= 3:
                    # Simple correlation analysis
                    large_backlogs = [(b, o) for b, o in backlog_data if b > 15]
                    small_backlogs = [(b, o) for b, o in backlog_data if b <= 15]
                    
                    if large_backlogs and small_backlogs:
                        large_avg = mean([o for b, o in large_backlogs])
                        small_avg = mean([o for b, o in small_backlogs])
                        
                        if abs(large_avg - small_avg) > 0.1:
                            better_group = "smaller" if small_avg > large_avg else "larger"
                            insights.append(PatternInsight(
                                pattern_type="backlog_correlation",
                                insight_text=f"Projects with {better_group} backlogs tend to perform better "
                                           f"({max(large_avg, small_avg):.1%} vs {min(large_avg, small_avg):.1%})",
                                confidence=0.5,
                                supporting_episodes=len(backlog_data)
                            ))
            
        except Exception as e:
            logger.warning(f"Outcome correlation analysis failed: {e}")
        
        return {'insights': insights}
    
    def calculate_pattern_confidence(
        self, 
        pattern: DecisionPattern, 
        total_episodes: int,
        context_similarity: float = 1.0
    ) -> float:
        """Calculate confidence score for a pattern"""
        try:
            # Base confidence on support ratio
            support_confidence = min(pattern.episode_count / max(total_episodes, 1), 1.0)
            
            # Adjust for success rate
            success_confidence = pattern.success_rate
            
            # Adjust for context similarity
            context_confidence = context_similarity
            
            # Combine factors (weighted average)
            combined_confidence = (
                support_confidence * 0.4 +
                success_confidence * 0.4 + 
                context_confidence * 0.2
            )
            
            return min(combined_confidence, 1.0)
            
        except Exception:
            return 0.0
    
    def filter_significant_patterns(
        self, 
        patterns: List[DecisionPattern], 
        insights: List[PatternInsight]
    ) -> Tuple[List[DecisionPattern], List[PatternInsight]]:
        """Filter patterns and insights by significance thresholds"""
        
        significant_patterns = [
            p for p in patterns 
            if p.confidence >= self.min_confidence_threshold 
            and p.success_rate >= self.success_threshold
        ]
        
        significant_insights = [
            i for i in insights 
            if i.confidence >= self.min_confidence_threshold
        ]
        
        return significant_patterns, significant_insights