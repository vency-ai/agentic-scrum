import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from uuid import UUID
import statistics
from services.strategy.strategy_repository import StrategyRepository

logger = logging.getLogger(__name__)

class LearningOptimizer:
    """
    Learning Optimizer - Continuously tunes strategy performance based on real-world outcomes
    
    Responsible for:
    - Analyzing strategy performance over time
    - Adjusting strategy confidence scores based on outcomes
    - Identifying underperforming strategies for deactivation
    - Optimizing strategy selection algorithms
    - Providing feedback for strategy improvement
    """
    
    def __init__(self, strategy_repository: StrategyRepository):
        self.strategy_repository = strategy_repository
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Optimization parameters
        self.performance_window_days = 30
        self.min_applications_for_optimization = 3
        self.confidence_adjustment_rate = 0.05  # 5% adjustment per optimization cycle
        self.underperformance_threshold = 0.4
        self.deactivation_threshold = 0.25
    
    async def optimize_strategy_performance(
        self,
        strategy_id: Optional[UUID] = None,
        optimization_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Optimize performance for a specific strategy or all active strategies"""
        try:
            if strategy_id:
                strategies_to_optimize = [await self.strategy_repository.get_strategy(strategy_id)]
                if not strategies_to_optimize[0]:
                    raise ValueError(f"Strategy {strategy_id} not found")
            else:
                strategies_to_optimize = await self.strategy_repository.get_active_strategies()
            
            optimization_results = {
                'strategies_analyzed': 0,
                'strategies_optimized': 0,
                'strategies_deactivated': 0,
                'confidence_adjustments': [],
                'deactivated_strategies': [],
                'performance_improvements': []
            }
            
            for strategy in strategies_to_optimize:
                if not strategy:
                    continue
                    
                optimization_results['strategies_analyzed'] += 1
                
                # Analyze recent performance
                performance_analysis = await self._analyze_strategy_performance(
                    strategy.knowledge_id
                )
                
                if not performance_analysis['sufficient_data']:
                    self.logger.debug(f"Insufficient data for strategy {strategy.knowledge_id} optimization")
                    continue
                
                # Decide optimization action
                optimization_action = await self._determine_optimization_action(
                    strategy, performance_analysis
                )
                
                if optimization_action['action'] == 'adjust_confidence':
                    await self._adjust_strategy_confidence(
                        strategy.knowledge_id,
                        optimization_action['new_confidence'],
                        optimization_action['reason']
                    )
                    optimization_results['strategies_optimized'] += 1
                    optimization_results['confidence_adjustments'].append({
                        'strategy_id': strategy.knowledge_id,
                        'old_confidence': strategy.confidence,
                        'new_confidence': optimization_action['new_confidence'],
                        'reason': optimization_action['reason']
                    })
                
                elif optimization_action['action'] == 'deactivate':
                    await self.strategy_repository.deactivate_strategy(
                        strategy.knowledge_id,
                        optimization_action['reason']
                    )
                    optimization_results['strategies_deactivated'] += 1
                    optimization_results['deactivated_strategies'].append({
                        'strategy_id': strategy.knowledge_id,
                        'reason': optimization_action['reason'],
                        'performance_data': performance_analysis
                    })
                
                elif optimization_action['action'] == 'performance_feedback':
                    optimization_results['performance_improvements'].append({
                        'strategy_id': strategy.knowledge_id,
                        'feedback': optimization_action['feedback']
                    })
            
            self.logger.info(
                f"Optimization complete: {optimization_results['strategies_analyzed']} analyzed, "
                f"{optimization_results['strategies_optimized']} optimized, "
                f"{optimization_results['strategies_deactivated']} deactivated"
            )
            
            return optimization_results
            
        except Exception as e:
            self.logger.error(f"Failed to optimize strategy performance: {e}")
            raise
    
    async def _analyze_strategy_performance(self, strategy_id: UUID) -> Dict[str, Any]:
        """Analyze recent performance data for a strategy"""
        try:
            # Get recent performance history
            performance_history = await self.strategy_repository.get_strategy_performance_history(
                strategy_id=strategy_id,
                days=self.performance_window_days
            )
            
            if len(performance_history) < self.min_applications_for_optimization:
                return {
                    'sufficient_data': False,
                    'application_count': len(performance_history)
                }
            
            # Calculate performance metrics
            outcome_qualities = [
                entry['outcome_quality'] for entry in performance_history
                if entry['outcome_quality'] is not None
            ]
            
            strategy_confidences = [
                entry['strategy_confidence'] for entry in performance_history
            ]
            
            performance_deltas = [
                entry['performance_delta'] for entry in performance_history
                if entry['performance_delta'] is not None
            ]
            
            # Statistical analysis
            analysis = {
                'sufficient_data': True,
                'application_count': len(performance_history),
                'performance_metrics': {
                    'avg_outcome_quality': statistics.mean(outcome_qualities) if outcome_qualities else 0,
                    'median_outcome_quality': statistics.median(outcome_qualities) if outcome_qualities else 0,
                    'outcome_quality_std': statistics.stdev(outcome_qualities) if len(outcome_qualities) > 1 else 0,
                    'min_outcome_quality': min(outcome_qualities) if outcome_qualities else 0,
                    'max_outcome_quality': max(outcome_qualities) if outcome_qualities else 0
                },
                'confidence_metrics': {
                    'avg_confidence': statistics.mean(strategy_confidences) if strategy_confidences else 0,
                    'confidence_consistency': 1 - (statistics.stdev(strategy_confidences) if len(strategy_confidences) > 1 else 0)
                },
                'performance_deltas': {
                    'avg_delta': statistics.mean(performance_deltas) if performance_deltas else 0,
                    'positive_deltas': len([d for d in performance_deltas if d and d > 0]),
                    'negative_deltas': len([d for d in performance_deltas if d and d < 0])
                },
                'trend_analysis': self._analyze_performance_trend(performance_history),
                'recent_applications': len([
                    entry for entry in performance_history
                    if entry['application_timestamp'] and
                    datetime.fromisoformat(entry['application_timestamp'].replace('Z', '+00:00')) >=
                    datetime.now().replace(tzinfo=None) - timedelta(days=7)
                ])
            }
            
            # Performance assessment
            analysis['overall_assessment'] = self._assess_overall_performance(analysis)
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Failed to analyze strategy performance: {e}")
            return {'sufficient_data': False, 'error': str(e)}
    
    def _analyze_performance_trend(self, performance_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze the trend in strategy performance over time"""
        if len(performance_history) < 3:
            return {'trend': 'insufficient_data'}
        
        # Sort by timestamp
        sorted_history = sorted(
            performance_history,
            key=lambda x: x['application_timestamp']
        )
        
        # Split into recent and older periods
        mid_point = len(sorted_history) // 2
        older_period = sorted_history[:mid_point]
        recent_period = sorted_history[mid_point:]
        
        # Calculate average quality for each period
        older_avg = statistics.mean([
            entry['outcome_quality'] for entry in older_period
            if entry['outcome_quality'] is not None
        ]) if older_period else 0
        
        recent_avg = statistics.mean([
            entry['outcome_quality'] for entry in recent_period
            if entry['outcome_quality'] is not None
        ]) if recent_period else 0
        
        # Determine trend
        trend_difference = recent_avg - older_avg
        
        if abs(trend_difference) < 0.05:
            trend = 'stable'
        elif trend_difference > 0.05:
            trend = 'improving'
        else:
            trend = 'declining'
        
        return {
            'trend': trend,
            'older_avg_quality': older_avg,
            'recent_avg_quality': recent_avg,
            'trend_difference': trend_difference
        }
    
    def _assess_overall_performance(self, analysis: Dict[str, Any]) -> str:
        """Assess overall strategy performance"""
        avg_quality = analysis['performance_metrics']['avg_outcome_quality']
        trend = analysis['trend_analysis']['trend']
        avg_delta = analysis['performance_deltas']['avg_delta']
        
        # Performance thresholds
        if avg_quality >= 0.8 and trend != 'declining' and avg_delta >= 0:
            return 'excellent'
        elif avg_quality >= 0.7 and trend != 'declining':
            return 'good'
        elif avg_quality >= 0.5 and trend == 'improving':
            return 'improving'
        elif avg_quality >= 0.4 and trend != 'declining':
            return 'acceptable'
        elif avg_quality >= 0.25:
            return 'underperforming'
        else:
            return 'poor'
    
    async def _determine_optimization_action(
        self,
        strategy,
        performance_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Determine what optimization action to take for a strategy"""
        assessment = performance_analysis['overall_assessment']
        avg_quality = performance_analysis['performance_metrics']['avg_outcome_quality']
        trend = performance_analysis['trend_analysis']['trend']
        current_confidence = strategy.confidence
        
        # Deactivation check
        if (assessment == 'poor' or 
            (assessment == 'underperforming' and trend == 'declining') or
            avg_quality <= self.deactivation_threshold):
            return {
                'action': 'deactivate',
                'reason': f"Poor performance: avg_quality={avg_quality:.3f}, trend={trend}, assessment={assessment}"
            }
        
        # Confidence adjustment
        if assessment in ['excellent', 'good']:
            # Increase confidence slightly
            new_confidence = min(1.0, current_confidence + self.confidence_adjustment_rate)
            if new_confidence != current_confidence:
                return {
                    'action': 'adjust_confidence',
                    'new_confidence': new_confidence,
                    'reason': f"Good performance: {assessment}, trend={trend}"
                }
        
        elif assessment in ['underperforming', 'acceptable'] and trend == 'declining':
            # Decrease confidence
            new_confidence = max(0.1, current_confidence - self.confidence_adjustment_rate)
            if new_confidence != current_confidence:
                return {
                    'action': 'adjust_confidence',
                    'new_confidence': new_confidence,
                    'reason': f"Declining performance: {assessment}, trend={trend}"
                }
        
        # No action needed
        return {
            'action': 'no_action',
            'reason': f"Performance stable: {assessment}, trend={trend}"
        }
    
    async def _adjust_strategy_confidence(
        self,
        strategy_id: UUID,
        new_confidence: float,
        reason: str
    ):
        """Adjust strategy confidence in the database"""
        try:
            if not self.strategy_repository.knowledge_store._pool:
                raise RuntimeError("Knowledge store not initialized")
            
            async with self.strategy_repository.knowledge_store._pool.acquire() as conn:
                await conn.execute("""
                    UPDATE agent_knowledge
                    SET confidence = $1, last_validated = $2
                    WHERE knowledge_id = $3
                """, new_confidence, datetime.utcnow(), strategy_id)
                
                self.logger.info(f"Adjusted confidence for strategy {strategy_id} to {new_confidence:.3f}: {reason}")
                
        except Exception as e:
            self.logger.error(f"Failed to adjust strategy confidence: {e}")
            raise
    
    async def identify_optimization_opportunities(self) -> Dict[str, Any]:
        """Identify strategies that could benefit from optimization"""
        try:
            opportunities = {
                'underperforming_strategies': [],
                'inconsistent_strategies': [],
                'unused_strategies': [],
                'high_potential_strategies': []
            }
            
            # Get underperforming strategies
            underperforming = await self.strategy_repository.get_underperforming_strategies(
                min_applications=self.min_applications_for_optimization,
                max_success_rate=self.underperformance_threshold,
                days=self.performance_window_days
            )
            
            opportunities['underperforming_strategies'] = [
                {'strategy_id': str(sid), 'success_rate': rate}
                for sid, rate in underperforming
            ]
            
            # Get active strategies for further analysis
            active_strategies = await self.strategy_repository.get_active_strategies(limit=100)
            
            for strategy in active_strategies:
                if strategy.times_applied == 0:
                    opportunities['unused_strategies'].append({
                        'strategy_id': str(strategy.knowledge_id),
                        'description': strategy.description,
                        'confidence': strategy.confidence,
                        'age_days': (datetime.utcnow() - strategy.created_at).days
                    })
                
                elif (strategy.times_applied >= 3 and 
                      strategy.confidence < 0.7 and 
                      strategy.success_rate and strategy.success_rate >= 0.8):
                    opportunities['high_potential_strategies'].append({
                        'strategy_id': str(strategy.knowledge_id),
                        'description': strategy.description,
                        'confidence': strategy.confidence,
                        'success_rate': strategy.success_rate,
                        'times_applied': strategy.times_applied
                    })
            
            return opportunities
            
        except Exception as e:
            self.logger.error(f"Failed to identify optimization opportunities: {e}")
            return {}
    
    async def generate_optimization_report(self) -> Dict[str, Any]:
        """Generate a comprehensive optimization report"""
        try:
            report = {
                'timestamp': datetime.utcnow().isoformat(),
                'optimization_parameters': {
                    'performance_window_days': self.performance_window_days,
                    'min_applications_for_optimization': self.min_applications_for_optimization,
                    'confidence_adjustment_rate': self.confidence_adjustment_rate,
                    'underperformance_threshold': self.underperformance_threshold,
                    'deactivation_threshold': self.deactivation_threshold
                }
            }
            
            # Get strategy analytics
            strategy_analytics = await self.strategy_repository.get_strategy_analytics()
            report['strategy_analytics'] = strategy_analytics
            
            # Get optimization opportunities
            opportunities = await self.identify_optimization_opportunities()
            report['optimization_opportunities'] = opportunities
            
            # Run optimization analysis on all strategies
            optimization_results = await self.optimize_strategy_performance()
            report['optimization_simulation'] = optimization_results
            
            return report
            
        except Exception as e:
            self.logger.error(f"Failed to generate optimization report: {e}")
            return {'error': str(e)}
    
    async def cleanup_performance_data(self):
        """Clean up old performance data"""
        try:
            deleted_count = await self.strategy_repository.cleanup_old_performance_logs(
                days_to_keep=self.performance_window_days * 3  # Keep 3x the analysis window
            )
            
            self.logger.info(f"Cleaned up {deleted_count} old performance log entries")
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup performance data: {e}")
            raise