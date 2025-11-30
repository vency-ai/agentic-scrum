import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
from uuid import UUID
from collections import defaultdict, Counter
import statistics
from memory.agent_memory_store import AgentMemoryStore
from memory.models import Episode

logger = logging.getLogger(__name__)

class PatternExtractor:
    """
    Pattern Extractor - Analyzes high-success episodes to identify patterns
    
    Responsible for:
    - Identifying episodes with high outcome quality (>= 0.85)
    - Extracting common decision patterns from successful episodes
    - Finding contextual similarities across high-performing decisions
    - Generating structured pattern data for strategy creation
    """
    
    def __init__(self, memory_store: AgentMemoryStore):
        self.memory_store = memory_store
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Pattern extraction thresholds
        self.min_success_threshold = 0.85
        self.min_pattern_frequency = 3  # Pattern must appear in at least 3 episodes
        self.min_confidence_threshold = 0.7
    
    async def extract_patterns_from_successful_episodes(
        self,
        project_id: Optional[str] = None,
        days_back: int = 30,
        min_episodes: int = 5
    ) -> List[Dict[str, Any]]:
        """Extract patterns from recent high-success episodes"""
        try:
            # Get high-success episodes
            successful_episodes = await self._get_successful_episodes(
                project_id=project_id,
                days_back=days_back,
                min_episodes=min_episodes
            )
            
            if len(successful_episodes) < min_episodes:
                self.logger.warning(f"Insufficient successful episodes ({len(successful_episodes)}) for pattern extraction")
                return []
            
            self.logger.info(f"Analyzing {len(successful_episodes)} successful episodes for patterns")
            
            # Extract different types of patterns
            patterns = []
            
            # 1. Decision context patterns
            context_patterns = await self._extract_context_patterns(successful_episodes)
            patterns.extend(context_patterns)
            
            # 2. Resource allocation patterns
            resource_patterns = await self._extract_resource_patterns(successful_episodes)
            patterns.extend(resource_patterns)
            
            # 3. Task ordering patterns
            task_patterns = await self._extract_task_patterns(successful_episodes)
            patterns.extend(task_patterns)
            
            # 4. Timing patterns
            timing_patterns = await self._extract_timing_patterns(successful_episodes)
            patterns.extend(timing_patterns)
            
            # Filter patterns by frequency and confidence
            validated_patterns = self._validate_patterns(patterns, successful_episodes)
            
            self.logger.info(f"Extracted {len(validated_patterns)} validated patterns from successful episodes")
            return validated_patterns
            
        except Exception as e:
            self.logger.error(f"Failed to extract patterns from successful episodes: {e}")
            raise
    
    async def _get_successful_episodes(
        self,
        project_id: Optional[str] = None,
        days_back: int = 30,
        min_episodes: int = 5
    ) -> List[Episode]:
        """Retrieve episodes with high outcome quality"""
        try:
            if not self.memory_store._pool:
                raise RuntimeError("Memory store not initialized")
            
            async with self.memory_store._pool.acquire() as conn:
                if project_id:
                    rows = await conn.fetch("""
                        SELECT * FROM agent_episodes
                        WHERE project_id = $1 
                        AND outcome_quality >= $2
                        AND timestamp >= NOW() - INTERVAL '%d days'
                        AND outcome IS NOT NULL
                        ORDER BY outcome_quality DESC, timestamp DESC
                    """ % days_back, project_id, self.min_success_threshold)
                else:
                    rows = await conn.fetch("""
                        SELECT * FROM agent_episodes
                        WHERE outcome_quality >= $1
                        AND timestamp >= NOW() - INTERVAL '%d days'
                        AND outcome IS NOT NULL
                        ORDER BY outcome_quality DESC, timestamp DESC
                    """ % days_back, self.min_success_threshold)
                
                episodes = [Episode.from_db_row(dict(row)) for row in rows]
                
                self.logger.debug(f"Found {len(episodes)} successful episodes (quality >= {self.min_success_threshold})")
                return episodes
                
        except Exception as e:
            self.logger.error(f"Failed to get successful episodes: {e}")
            raise
    
    async def _extract_context_patterns(self, episodes: List[Episode]) -> List[Dict[str, Any]]:
        """Extract patterns from decision contexts"""
        patterns = []
        
        try:
            # Group episodes by similar context characteristics
            context_groups = defaultdict(list)
            
            for episode in episodes:
                if not episode.perception or 'project_context' not in episode.perception:
                    continue
                
                context = episode.perception['project_context']
                
                # Create context signature for grouping
                signature = self._create_context_signature(context)
                context_groups[signature].append(episode)
            
            # Extract patterns from groups with sufficient frequency
            for signature, group_episodes in context_groups.items():
                if len(group_episodes) >= self.min_pattern_frequency:
                    pattern = await self._analyze_context_group(signature, group_episodes)
                    if pattern:
                        patterns.append(pattern)
            
            return patterns
            
        except Exception as e:
            self.logger.error(f"Failed to extract context patterns: {e}")
            return []
    
    def _create_context_signature(self, context: Dict[str, Any]) -> str:
        """Create a signature for grouping similar contexts"""
        # Extract key context features for grouping
        features = []
        
        # Project characteristics
        if 'team_size' in context:
            team_size = context['team_size']
            if team_size <= 3:
                features.append('small_team')
            elif team_size <= 8:
                features.append('medium_team')
            else:
                features.append('large_team')
        
        if 'project_type' in context:
            features.append(f"type_{context['project_type']}")
        
        if 'complexity' in context:
            complexity = context['complexity']
            if complexity <= 0.3:
                features.append('low_complexity')
            elif complexity <= 0.7:
                features.append('medium_complexity')
            else:
                features.append('high_complexity')
        
        # Resource availability
        if 'resource_availability' in context:
            availability = context['resource_availability']
            if availability >= 0.8:
                features.append('high_resources')
            elif availability >= 0.5:
                features.append('medium_resources')
            else:
                features.append('low_resources')
        
        return '_'.join(sorted(features))
    
    async def _analyze_context_group(self, signature: str, episodes: List[Episode]) -> Optional[Dict[str, Any]]:
        """Analyze a group of episodes with similar contexts"""
        try:
            # Calculate average outcome quality
            qualities = [ep.outcome_quality for ep in episodes if ep.outcome_quality is not None]
            avg_quality = statistics.mean(qualities) if qualities else 0
            
            if avg_quality < self.min_confidence_threshold:
                return None
            
            # Extract common decision patterns
            common_decisions = self._find_common_decisions(episodes)
            
            # Extract context characteristics
            context_chars = self._extract_context_characteristics(episodes)
            
            pattern = {
                'pattern_type': 'context_pattern',
                'pattern_id': f"context_{signature}",
                'description': f"Decision pattern for {signature.replace('_', ' ')} contexts",
                'context_signature': signature,
                'context_characteristics': context_chars,
                'common_decisions': common_decisions,
                'supporting_episodes': [ep.episode_id for ep in episodes],
                'frequency': len(episodes),
                'average_outcome_quality': avg_quality,
                'confidence': min(avg_quality, len(episodes) / 10.0),  # Cap at 1.0
                'applicability_conditions': self._generate_applicability_conditions(signature, context_chars)
            }
            
            return pattern
            
        except Exception as e:
            self.logger.error(f"Failed to analyze context group: {e}")
            return None
    
    def _find_common_decisions(self, episodes: List[Episode]) -> Dict[str, Any]:
        """Find common decision patterns across episodes"""
        decisions = defaultdict(list)
        
        for episode in episodes:
            if not episode.action:
                continue
                
            action = episode.action
            
            # Extract task-related decisions
            if 'task_adjustments' in action:
                decisions['task_adjustments'].extend(action['task_adjustments'])
            
            if 'resource_allocation' in action:
                decisions['resource_allocation'].append(action['resource_allocation'])
            
            if 'schedule_adjustments' in action:
                decisions['schedule_adjustments'].append(action['schedule_adjustments'])
            
            if 'intelligence_enhancement' in action:
                decisions['intelligence_enhancements'].append(action['intelligence_enhancement'])
        
        # Find frequent patterns in each decision type
        common = {}
        
        for decision_type, decision_list in decisions.items():
            if len(decision_list) >= self.min_pattern_frequency:
                common[decision_type] = self._analyze_decision_frequency(decision_list)
        
        return common
    
    def _analyze_decision_frequency(self, decisions: List[Any]) -> Dict[str, Any]:
        """Analyze frequency of specific decision types"""
        if not decisions:
            return {}
        
        # For now, simple frequency analysis
        # TODO: Implement more sophisticated pattern analysis
        return {
            'frequency': len(decisions),
            'sample_decisions': decisions[:3],  # Keep first 3 as examples
            'pattern_strength': len(decisions) / 10.0  # Normalize to 0-1
        }
    
    def _extract_context_characteristics(self, episodes: List[Episode]) -> Dict[str, Any]:
        """Extract common characteristics from episode contexts"""
        chars = defaultdict(list)
        
        for episode in episodes:
            if not episode.perception or 'project_context' not in episode.perception:
                continue
                
            context = episode.perception['project_context']
            
            for key, value in context.items():
                if isinstance(value, (int, float)):
                    chars[key].append(value)
                elif isinstance(value, str):
                    chars[key].append(value)
        
        # Calculate statistics for numeric values
        characteristics = {}
        for key, values in chars.items():
            if not values:
                continue
                
            if isinstance(values[0], (int, float)):
                characteristics[key] = {
                    'mean': statistics.mean(values),
                    'median': statistics.median(values),
                    'min': min(values),
                    'max': max(values)
                }
            else:
                # For categorical values, find most common
                counter = Counter(values)
                characteristics[key] = {
                    'most_common': counter.most_common(3),
                    'distinct_count': len(counter)
                }
        
        return characteristics
    
    def _generate_applicability_conditions(self, signature: str, context_chars: Dict[str, Any]) -> Dict[str, Any]:
        """Generate conditions for when this pattern should be applied"""
        conditions = {'context_signature': signature}
        
        # Convert characteristics to applicability rules
        for key, char_data in context_chars.items():
            if isinstance(char_data, dict) and 'mean' in char_data:
                # Numeric conditions - use mean +/- 20%
                mean = char_data['mean']
                conditions[key] = {
                    'min': mean * 0.8,
                    'max': mean * 1.2
                }
            elif isinstance(char_data, dict) and 'most_common' in char_data:
                # Categorical conditions - use most common values
                conditions[key] = [item[0] for item in char_data['most_common'][:2]]
        
        return conditions
    
    async def _extract_resource_patterns(self, episodes: List[Episode]) -> List[Dict[str, Any]]:
        """Extract resource allocation patterns"""
        # TODO: Implement resource pattern extraction
        self.logger.debug("Resource pattern extraction not yet implemented")
        return []
    
    async def _extract_task_patterns(self, episodes: List[Episode]) -> List[Dict[str, Any]]:
        """Extract task ordering and management patterns"""
        # TODO: Implement task pattern extraction
        self.logger.debug("Task pattern extraction not yet implemented")
        return []
    
    async def _extract_timing_patterns(self, episodes: List[Episode]) -> List[Dict[str, Any]]:
        """Extract timing and scheduling patterns"""
        # TODO: Implement timing pattern extraction
        self.logger.debug("Timing pattern extraction not yet implemented")
        return []
    
    def _validate_patterns(self, patterns: List[Dict[str, Any]], episodes: List[Episode]) -> List[Dict[str, Any]]:
        """Validate patterns against frequency and confidence thresholds"""
        validated = []
        
        for pattern in patterns:
            if (pattern.get('frequency', 0) >= self.min_pattern_frequency and
                pattern.get('confidence', 0) >= self.min_confidence_threshold):
                validated.append(pattern)
        
        return validated
    
    async def get_pattern_extraction_stats(self) -> Dict[str, Any]:
        """Get statistics about pattern extraction performance"""
        try:
            if not self.memory_store._pool:
                raise RuntimeError("Memory store not initialized")
            
            async with self.memory_store._pool.acquire() as conn:
                stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total_episodes,
                        COUNT(CASE WHEN outcome_quality >= $1 THEN 1 END) as successful_episodes,
                        AVG(outcome_quality) as avg_quality,
                        COUNT(CASE WHEN outcome_quality >= $1 AND timestamp >= NOW() - INTERVAL '7 days' THEN 1 END) as recent_successful
                    FROM agent_episodes
                    WHERE outcome IS NOT NULL
                """, self.min_success_threshold)
                
                return dict(stats) if stats else {}
                
        except Exception as e:
            self.logger.error(f"Failed to get pattern extraction stats: {e}")
            return {}