import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import UUID
from memory.agent_memory_store import AgentMemoryStore
from memory.knowledge_store import KnowledgeStore
from services.strategy.pattern_extractor import PatternExtractor
from services.strategy.strategy_generator import StrategyGenerator
from services.strategy.strategy_repository import StrategyRepository
from services.strategy.learning_optimizer import LearningOptimizer
from config.feature_flags import FeatureFlags

logger = logging.getLogger(__name__)

class StrategyEvolver:
    """
    Strategy Evolver - Main orchestrator for the Strategy Evolution Layer
    
    Responsible for:
    - Orchestrating the complete strategy evolution pipeline
    - Coordinating pattern extraction, strategy generation, and optimization
    - Managing the daily strategy evolution process
    - Providing unified interface for strategy evolution operations
    - Monitoring and reporting on evolution performance
    """
    
    def __init__(
        self,
        memory_store: AgentMemoryStore,
        knowledge_store: KnowledgeStore,
        feature_flags: FeatureFlags
    ):
        self.memory_store = memory_store
        self.knowledge_store = knowledge_store
        self.feature_flags = feature_flags
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Initialize strategy evolution components
        self.strategy_repository = StrategyRepository(knowledge_store)
        self.pattern_extractor = PatternExtractor(memory_store)
        self.strategy_generator = StrategyGenerator(self.pattern_extractor, self.strategy_repository)
        self.learning_optimizer = LearningOptimizer(self.strategy_repository)
        
        # Evolution parameters
        self.evolution_enabled = feature_flags.ENABLE_STRATEGY_EVOLUTION if feature_flags else False
        self.min_episodes_for_evolution = 10
        self.pattern_extraction_days = 30
        self.max_strategies_per_evolution = 20
    
    async def run_daily_evolution(self) -> Dict[str, Any]:
        """Run the complete daily strategy evolution process"""
        if not self.evolution_enabled:
            self.logger.info("Strategy evolution is disabled by feature flag")
            return {'status': 'disabled', 'reason': 'feature_flag_disabled'}
        
        evolution_start_time = datetime.utcnow()
        self.logger.info("Starting daily strategy evolution process")
        
        try:
            evolution_results = {
                'timestamp': evolution_start_time.isoformat(),
                'status': 'in_progress',
                'phases': {}
            }
            
            # Phase 1: Extract patterns from successful episodes
            self.logger.info("Phase 1: Extracting patterns from successful episodes")
            pattern_results = await self._extract_patterns_phase()
            evolution_results['phases']['pattern_extraction'] = pattern_results
            
            if not pattern_results['success']:
                evolution_results['status'] = 'failed'
                evolution_results['failure_reason'] = 'pattern_extraction_failed'
                return evolution_results
            
            # Phase 2: Generate new strategies from patterns
            self.logger.info("Phase 2: Generating strategies from extracted patterns")
            generation_results = await self._generate_strategies_phase(pattern_results['patterns'])
            evolution_results['phases']['strategy_generation'] = generation_results
            
            # Phase 3: Optimize existing strategies
            self.logger.info("Phase 3: Optimizing existing strategy performance")
            optimization_results = await self._optimize_strategies_phase()
            evolution_results['phases']['strategy_optimization'] = optimization_results
            
            # Phase 4: Cleanup and maintenance
            self.logger.info("Phase 4: Performing cleanup and maintenance")
            cleanup_results = await self._cleanup_phase()
            evolution_results['phases']['cleanup'] = cleanup_results
            
            # Calculate overall results
            evolution_duration = (datetime.utcnow() - evolution_start_time).total_seconds()
            evolution_results.update({
                'status': 'completed',
                'duration_seconds': evolution_duration,
                'summary': self._generate_evolution_summary(evolution_results['phases'])
            })
            
            self.logger.info(f"Daily strategy evolution completed in {evolution_duration:.1f} seconds")
            return evolution_results
            
        except Exception as e:
            self.logger.error(f"Daily strategy evolution failed: {e}")
            evolution_results.update({
                'status': 'failed',
                'error_message': str(e),
                'duration_seconds': (datetime.utcnow() - evolution_start_time).total_seconds()
            })
            return evolution_results
    
    async def _extract_patterns_phase(self) -> Dict[str, Any]:
        """Execute pattern extraction phase"""
        try:
            # Check if we have sufficient episodes
            total_episodes = await self.memory_store.get_episode_count()
            if total_episodes < self.min_episodes_for_evolution:
                return {
                    'success': False,
                    'reason': 'insufficient_episodes',
                    'total_episodes': total_episodes,
                    'required_episodes': self.min_episodes_for_evolution
                }
            
            # Extract patterns from all projects
            patterns = await self.pattern_extractor.extract_patterns_from_successful_episodes(
                project_id=None,  # All projects
                days_back=self.pattern_extraction_days,
                min_episodes=5
            )
            
            # Get extraction statistics
            extraction_stats = await self.pattern_extractor.get_pattern_extraction_stats()
            
            return {
                'success': True,
                'patterns': patterns,
                'pattern_count': len(patterns),
                'extraction_stats': extraction_stats,
                'parameters': {
                    'days_back': self.pattern_extraction_days,
                    'min_episodes': 5
                }
            }
            
        except Exception as e:
            self.logger.error(f"Pattern extraction phase failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _generate_strategies_phase(self, patterns: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Execute strategy generation phase"""
        try:
            if not patterns:
                return {
                    'success': True,
                    'strategies_generated': 0,
                    'reason': 'no_patterns_available'
                }
            
            # Limit number of strategies to generate
            patterns_to_use = patterns[:self.max_strategies_per_evolution]
            
            # Generate strategies from patterns
            generation_context = {
                'evolution_timestamp': datetime.utcnow().isoformat(),
                'pattern_count': len(patterns),
                'evolution_type': 'daily_evolution'
            }
            
            generated_strategy_ids = await self.strategy_generator.generate_strategies_from_patterns(
                patterns=patterns_to_use,
                generation_context=generation_context
            )
            
            # Get generation statistics
            generation_stats = await self.strategy_generator.get_generation_statistics()
            
            return {
                'success': True,
                'strategies_generated': len(generated_strategy_ids),
                'strategy_ids': [str(sid) for sid in generated_strategy_ids],
                'patterns_processed': len(patterns_to_use),
                'patterns_available': len(patterns),
                'generation_stats': generation_stats
            }
            
        except Exception as e:
            self.logger.error(f"Strategy generation phase failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _optimize_strategies_phase(self) -> Dict[str, Any]:
        """Execute strategy optimization phase"""
        try:
            # Run optimization on all active strategies
            optimization_results = await self.learning_optimizer.optimize_strategy_performance()
            
            # Get optimization opportunities
            opportunities = await self.learning_optimizer.identify_optimization_opportunities()
            
            return {
                'success': True,
                'optimization_results': optimization_results,
                'optimization_opportunities': opportunities
            }
            
        except Exception as e:
            self.logger.error(f"Strategy optimization phase failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _cleanup_phase(self) -> Dict[str, Any]:
        """Execute cleanup and maintenance phase"""
        try:
            cleanup_results = {}
            
            # Clean up old performance logs
            deleted_logs = await self.learning_optimizer.cleanup_performance_data()
            cleanup_results['performance_logs_deleted'] = deleted_logs
            
            # Get repository analytics for reporting
            analytics = await self.strategy_repository.get_strategy_analytics()
            cleanup_results['repository_analytics'] = analytics
            
            return {
                'success': True,
                'cleanup_results': cleanup_results
            }
            
        except Exception as e:
            self.logger.error(f"Cleanup phase failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _generate_evolution_summary(self, phases: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary of evolution results"""
        summary = {
            'phases_completed': 0,
            'phases_failed': 0,
            'total_phases': len(phases)
        }
        
        # Count phase results
        for phase_name, phase_result in phases.items():
            if phase_result.get('success', False):
                summary['phases_completed'] += 1
            else:
                summary['phases_failed'] += 1
        
        # Extract key metrics
        pattern_phase = phases.get('pattern_extraction', {})
        generation_phase = phases.get('strategy_generation', {})
        optimization_phase = phases.get('strategy_optimization', {})
        
        summary.update({
            'patterns_extracted': pattern_phase.get('pattern_count', 0),
            'strategies_generated': generation_phase.get('strategies_generated', 0),
            'strategies_optimized': optimization_phase.get('optimization_results', {}).get('strategies_optimized', 0),
            'strategies_deactivated': optimization_phase.get('optimization_results', {}).get('strategies_deactivated', 0)
        })
        
        # Overall success determination
        summary['overall_success'] = summary['phases_failed'] == 0
        
        return summary
    
    async def evolve_for_project(self, project_id: str) -> Dict[str, Any]:
        """Run targeted strategy evolution for a specific project"""
        try:
            self.logger.info(f"Running targeted strategy evolution for project {project_id}")
            
            evolution_results = {
                'project_id': project_id,
                'timestamp': datetime.utcnow().isoformat(),
                'status': 'in_progress'
            }
            
            # Extract patterns for this project only
            patterns = await self.pattern_extractor.extract_patterns_from_successful_episodes(
                project_id=project_id,
                days_back=self.pattern_extraction_days,
                min_episodes=3  # Lower threshold for project-specific evolution
            )
            
            evolution_results['patterns_extracted'] = len(patterns)
            
            if patterns:
                # Generate strategies from project patterns
                generated_ids = await self.strategy_generator.generate_strategies_from_patterns(
                    patterns=patterns,
                    generation_context={
                        'evolution_type': 'project_targeted',
                        'project_id': project_id,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )
                evolution_results['strategies_generated'] = len(generated_ids)
                evolution_results['strategy_ids'] = [str(sid) for sid in generated_ids]
            else:
                evolution_results['strategies_generated'] = 0
                evolution_results['strategy_ids'] = []
            
            evolution_results['status'] = 'completed'
            
            self.logger.info(
                f"Project evolution completed: {len(patterns)} patterns, "
                f"{evolution_results['strategies_generated']} strategies generated"
            )
            
            return evolution_results
            
        except Exception as e:
            self.logger.error(f"Project evolution failed for {project_id}: {e}")
            return {
                'project_id': project_id,
                'status': 'failed',
                'error': str(e)
            }
    
    async def get_evolution_status(self) -> Dict[str, Any]:
        """Get current status of the strategy evolution system"""
        try:
            # Get repository analytics
            repository_stats = await self.strategy_repository.get_strategy_analytics()
            
            # Get pattern extraction stats
            pattern_stats = await self.pattern_extractor.get_pattern_extraction_stats()
            
            # Get optimization opportunities
            optimization_opportunities = await self.learning_optimizer.identify_optimization_opportunities()
            
            return {
                'system_status': 'operational' if self.evolution_enabled else 'disabled',
                'feature_flag_enabled': self.evolution_enabled,
                'configuration': {
                    'min_episodes_for_evolution': self.min_episodes_for_evolution,
                    'pattern_extraction_days': self.pattern_extraction_days,
                    'max_strategies_per_evolution': self.max_strategies_per_evolution
                },
                'repository_stats': repository_stats,
                'pattern_extraction_stats': pattern_stats,
                'optimization_opportunities': optimization_opportunities,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get evolution status: {e}")
            return {
                'system_status': 'error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    async def force_strategy_evolution(self, force_parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Force run strategy evolution with custom parameters (for testing/admin use)"""
        try:
            # Temporarily override parameters if provided
            original_enabled = self.evolution_enabled
            original_min_episodes = self.min_episodes_for_evolution
            
            if force_parameters:
                self.evolution_enabled = force_parameters.get('enabled', True)
                self.min_episodes_for_evolution = force_parameters.get('min_episodes', 1)
            else:
                self.evolution_enabled = True  # Force enable for this run
            
            self.logger.info("Forcing strategy evolution with custom parameters")
            
            # Run the evolution
            results = await self.run_daily_evolution()
            results['forced_evolution'] = True
            results['force_parameters'] = force_parameters
            
            # Restore original parameters
            self.evolution_enabled = original_enabled
            self.min_episodes_for_evolution = original_min_episodes
            
            return results
            
        except Exception as e:
            self.logger.error(f"Forced strategy evolution failed: {e}")
            return {
                'status': 'failed',
                'error': str(e),
                'forced_evolution': True
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all strategy evolution components"""
        try:
            health_status = {
                'overall_status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'components': {}
            }
            
            # Check memory store
            memory_health = await self.memory_store.health_check()
            health_status['components']['memory_store'] = memory_health
            
            # Check knowledge store
            knowledge_health = await self.knowledge_store.health_check()
            health_status['components']['knowledge_store'] = {
                'status': 'ok' if knowledge_health else 'error'
            }
            
            # Check feature flags
            health_status['components']['feature_flags'] = {
                'strategy_evolution_enabled': self.evolution_enabled,
                'status': 'ok'
            }
            
            # Determine overall health
            component_statuses = [
                comp.get('status', 'unknown') for comp in health_status['components'].values()
            ]
            
            if 'error' in component_statuses:
                health_status['overall_status'] = 'degraded'
            elif 'unknown' in component_statuses:
                health_status['overall_status'] = 'unknown'
            
            return health_status
            
        except Exception as e:
            self.logger.error(f"Health check failed: {e}")
            return {
                'overall_status': 'error',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }