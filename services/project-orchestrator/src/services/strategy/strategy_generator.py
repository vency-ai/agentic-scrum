import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from uuid import UUID
import json
from services.strategy.pattern_extractor import PatternExtractor
from services.strategy.strategy_repository import StrategyRepository

logger = logging.getLogger(__name__)

class StrategyGenerator:
    """
    Strategy Generator - Converts extracted patterns into formal strategy objects
    
    Responsible for:
    - Converting pattern data into structured strategy definitions
    - Calculating strategy confidence scores
    - Generating strategy application rules and conditions
    - Creating strategy metadata and documentation
    """
    
    def __init__(self, pattern_extractor: PatternExtractor, strategy_repository: StrategyRepository):
        self.pattern_extractor = pattern_extractor
        self.strategy_repository = strategy_repository
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Strategy generation thresholds
        self.min_pattern_confidence = 0.6
        self.min_pattern_frequency = 3
    
    async def generate_strategies_from_patterns(
        self,
        patterns: List[Dict[str, Any]],
        generation_context: Optional[Dict[str, Any]] = None
    ) -> List[UUID]:
        """Generate formal strategy objects from extracted patterns"""
        try:
            generated_strategies = []
            
            for pattern in patterns:
                if not self._is_pattern_viable(pattern):
                    self.logger.debug(f"Skipping non-viable pattern: {pattern.get('pattern_id')}")
                    continue
                
                strategy_data = await self._convert_pattern_to_strategy(pattern, generation_context)
                
                if strategy_data:
                    strategy_id = await self.strategy_repository.create_strategy(
                        pattern_data=strategy_data,
                        confidence=strategy_data['confidence'],
                        description=strategy_data['description'],
                        created_by="strategy_generator"
                    )
                    
                    generated_strategies.append(strategy_id)
                    self.logger.info(f"Generated strategy {strategy_id} from pattern {pattern.get('pattern_id')}")
            
            self.logger.info(f"Generated {len(generated_strategies)} strategies from {len(patterns)} patterns")
            return generated_strategies
            
        except Exception as e:
            self.logger.error(f"Failed to generate strategies from patterns: {e}")
            raise
    
    def _is_pattern_viable(self, pattern: Dict[str, Any]) -> bool:
        """Check if pattern meets minimum criteria for strategy generation"""
        confidence = pattern.get('confidence', 0)
        frequency = pattern.get('frequency', 0)
        avg_quality = pattern.get('average_outcome_quality', 0)
        
        return (confidence >= self.min_pattern_confidence and
                frequency >= self.min_pattern_frequency and
                avg_quality >= 0.7)
    
    async def _convert_pattern_to_strategy(
        self,
        pattern: Dict[str, Any],
        generation_context: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Convert a pattern into a formal strategy structure"""
        try:
            pattern_type = pattern.get('pattern_type')
            
            if pattern_type == 'context_pattern':
                return await self._generate_context_strategy(pattern, generation_context)
            elif pattern_type == 'resource_pattern':
                return await self._generate_resource_strategy(pattern, generation_context)
            elif pattern_type == 'task_pattern':
                return await self._generate_task_strategy(pattern, generation_context)
            elif pattern_type == 'timing_pattern':
                return await self._generate_timing_strategy(pattern, generation_context)
            else:
                self.logger.warning(f"Unknown pattern type: {pattern_type}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to convert pattern to strategy: {e}")
            return None
    
    async def _generate_context_strategy(
        self,
        pattern: Dict[str, Any],
        generation_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate strategy from context pattern"""
        context_signature = pattern.get('context_signature', 'unknown')
        context_chars = pattern.get('context_characteristics', {})
        common_decisions = pattern.get('common_decisions', {})
        
        # Build strategy content
        strategy_content = {
            'strategy_type': 'context_based',
            'context_signature': context_signature,
            'applicability_conditions': pattern.get('applicability_conditions', {}),
            'decision_rules': self._build_decision_rules(common_decisions),
            'confidence_factors': self._calculate_confidence_factors(pattern),
            'performance_expectations': {
                'expected_outcome_quality': pattern.get('average_outcome_quality', 0.8),
                'success_probability': min(pattern.get('confidence', 0.7), 0.95),
                'risk_level': self._assess_risk_level(pattern)
            },
            'context_requirements': context_chars,
            'supporting_evidence': {
                'pattern_frequency': pattern.get('frequency', 0),
                'supporting_episodes': pattern.get('supporting_episodes', []),
                'historical_success_rate': pattern.get('average_outcome_quality', 0)
            }
        }
        
        # Generate description
        description = self._generate_strategy_description(context_signature, common_decisions, pattern)
        
        # Calculate final confidence score
        confidence = self._calculate_strategy_confidence(pattern, strategy_content)
        
        return {
            'strategy_type': 'context_based',
            'content': strategy_content,
            'description': description,
            'confidence': confidence,
            'supporting_episodes': pattern.get('supporting_episodes', []),
            'pattern_id': pattern.get('pattern_id'),
            'generation_timestamp': datetime.utcnow().isoformat(),
            'generation_context': generation_context or {}
        }
    
    def _build_decision_rules(self, common_decisions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Build decision rules from common decision patterns"""
        rules = []
        
        for decision_type, decision_data in common_decisions.items():
            if not isinstance(decision_data, dict) or 'frequency' not in decision_data:
                continue
            
            rule = {
                'rule_type': decision_type,
                'frequency': decision_data['frequency'],
                'pattern_strength': decision_data.get('pattern_strength', 0.5),
                'sample_decisions': decision_data.get('sample_decisions', []),
                'application_weight': min(decision_data.get('pattern_strength', 0.5), 1.0)
            }
            
            # Add specific rule logic based on decision type
            if decision_type == 'task_adjustments':
                rule['adjustment_guidelines'] = self._extract_task_adjustment_guidelines(decision_data)
            elif decision_type == 'resource_allocation':
                rule['allocation_guidelines'] = self._extract_resource_allocation_guidelines(decision_data)
            elif decision_type == 'schedule_adjustments':
                rule['schedule_guidelines'] = self._extract_schedule_adjustment_guidelines(decision_data)
            
            rules.append(rule)
        
        return rules
    
    def _extract_task_adjustment_guidelines(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract guidelines for task adjustments"""
        sample_decisions = decision_data.get('sample_decisions', [])
        
        # Analyze sample decisions to create guidelines
        guidelines = {
            'common_patterns': [],
            'adjustment_types': [],
            'magnitude_guidance': {}
        }
        
        # Simple analysis - in practice, this would be more sophisticated
        for decision in sample_decisions[:5]:  # Analyze first 5 samples
            if isinstance(decision, dict):
                if 'adjustment_type' in decision:
                    guidelines['adjustment_types'].append(decision['adjustment_type'])
                if 'magnitude' in decision:
                    if 'magnitude' not in guidelines['magnitude_guidance']:
                        guidelines['magnitude_guidance']['magnitude'] = []
                    guidelines['magnitude_guidance']['magnitude'].append(decision['magnitude'])
        
        return guidelines
    
    def _extract_resource_allocation_guidelines(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract guidelines for resource allocation"""
        # TODO: Implement resource allocation guidelines extraction
        return {'placeholder': 'resource_allocation_guidelines'}
    
    def _extract_schedule_adjustment_guidelines(self, decision_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract guidelines for schedule adjustments"""
        # TODO: Implement schedule adjustment guidelines extraction
        return {'placeholder': 'schedule_adjustment_guidelines'}
    
    def _calculate_confidence_factors(self, pattern: Dict[str, Any]) -> Dict[str, float]:
        """Calculate factors that contribute to strategy confidence"""
        return {
            'pattern_frequency_score': min(pattern.get('frequency', 0) / 10.0, 1.0),
            'outcome_quality_score': pattern.get('average_outcome_quality', 0),
            'consistency_score': pattern.get('confidence', 0),
            'evidence_strength_score': min(len(pattern.get('supporting_episodes', [])) / 20.0, 1.0)
        }
    
    def _assess_risk_level(self, pattern: Dict[str, Any]) -> str:
        """Assess risk level for strategy application"""
        frequency = pattern.get('frequency', 0)
        outcome_quality = pattern.get('average_outcome_quality', 0)
        confidence = pattern.get('confidence', 0)
        
        # Simple risk assessment - in practice, this would be more sophisticated
        risk_score = (frequency / 10.0 + outcome_quality + confidence) / 3.0
        
        if risk_score >= 0.8:
            return 'low'
        elif risk_score >= 0.6:
            return 'medium'
        else:
            return 'high'
    
    def _generate_strategy_description(
        self,
        context_signature: str,
        common_decisions: Dict[str, Any],
        pattern: Dict[str, Any]
    ) -> str:
        """Generate human-readable description for strategy"""
        base_context = context_signature.replace('_', ' ').title()
        
        decision_types = list(common_decisions.keys())
        if decision_types:
            decision_summary = ', '.join(decision_types[:2])  # First 2 decision types
            if len(decision_types) > 2:
                decision_summary += f" and {len(decision_types) - 2} other patterns"
        else:
            decision_summary = "decision patterns"
        
        frequency = pattern.get('frequency', 0)
        quality = pattern.get('average_outcome_quality', 0)
        
        description = (f"Strategy for {base_context} contexts focusing on {decision_summary}. "
                      f"Based on {frequency} successful episodes with {quality:.1%} average outcome quality.")
        
        return description
    
    def _calculate_strategy_confidence(
        self,
        pattern: Dict[str, Any],
        strategy_content: Dict[str, Any]
    ) -> float:
        """Calculate overall confidence score for the generated strategy"""
        confidence_factors = strategy_content.get('confidence_factors', {})
        
        # Weighted average of confidence factors
        weights = {
            'pattern_frequency_score': 0.2,
            'outcome_quality_score': 0.4,
            'consistency_score': 0.3,
            'evidence_strength_score': 0.1
        }
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for factor, weight in weights.items():
            if factor in confidence_factors:
                weighted_sum += confidence_factors[factor] * weight
                total_weight += weight
        
        if total_weight > 0:
            confidence = weighted_sum / total_weight
        else:
            confidence = pattern.get('confidence', 0.5)
        
        # Ensure confidence is within valid range
        return max(0.0, min(1.0, confidence))
    
    async def _generate_resource_strategy(
        self,
        pattern: Dict[str, Any],
        generation_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate strategy from resource pattern"""
        # TODO: Implement resource strategy generation
        self.logger.debug("Resource strategy generation not yet implemented")
        return {}
    
    async def _generate_task_strategy(
        self,
        pattern: Dict[str, Any],
        generation_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate strategy from task pattern"""
        # TODO: Implement task strategy generation
        self.logger.debug("Task strategy generation not yet implemented")
        return {}
    
    async def _generate_timing_strategy(
        self,
        pattern: Dict[str, Any],
        generation_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate strategy from timing pattern"""
        # TODO: Implement timing strategy generation
        self.logger.debug("Timing strategy generation not yet implemented")
        return {}
    
    async def update_strategy_from_feedback(
        self,
        strategy_id: UUID,
        feedback_data: Dict[str, Any]
    ):
        """Update strategy based on application feedback"""
        try:
            # Get current strategy
            strategy = await self.strategy_repository.get_strategy(strategy_id)
            if not strategy:
                raise ValueError(f"Strategy {strategy_id} not found")
            
            # Analyze feedback and update strategy content
            updated_content = self._incorporate_feedback(strategy.content, feedback_data)
            
            # Update confidence based on feedback
            updated_confidence = self._adjust_confidence_from_feedback(
                strategy.confidence, feedback_data
            )
            
            # TODO: Implement strategy update mechanism
            self.logger.info(f"Updated strategy {strategy_id} based on feedback")
            
        except Exception as e:
            self.logger.error(f"Failed to update strategy from feedback: {e}")
            raise
    
    def _incorporate_feedback(
        self,
        current_content: Dict[str, Any],
        feedback_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Incorporate feedback into strategy content"""
        # TODO: Implement feedback incorporation logic
        return current_content
    
    def _adjust_confidence_from_feedback(
        self,
        current_confidence: float,
        feedback_data: Dict[str, Any]
    ) -> float:
        """Adjust strategy confidence based on application feedback"""
        outcome_quality = feedback_data.get('outcome_quality', 0.5)
        
        # Simple confidence adjustment - move towards actual performance
        adjustment_factor = 0.1  # How much to adjust (10%)
        target_confidence = (current_confidence * 0.8) + (outcome_quality * 0.2)
        
        adjusted_confidence = current_confidence + (target_confidence - current_confidence) * adjustment_factor
        
        return max(0.0, min(1.0, adjusted_confidence))
    
    async def get_generation_statistics(self) -> Dict[str, Any]:
        """Get statistics about strategy generation performance"""
        try:
            # Get pattern extraction stats
            pattern_stats = await self.pattern_extractor.get_pattern_extraction_stats()
            
            # Get strategy repository stats
            strategy_stats = await self.strategy_repository.get_strategy_analytics()
            
            return {
                'pattern_extraction': pattern_stats,
                'strategy_repository': strategy_stats,
                'generation_thresholds': {
                    'min_pattern_confidence': self.min_pattern_confidence,
                    'min_pattern_frequency': self.min_pattern_frequency
                }
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get generation statistics: {e}")
            return {}