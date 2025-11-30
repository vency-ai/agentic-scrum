"""
Tests for Strategy Evolution Layer components

These tests verify the functionality of the strategy evolution components
including pattern extraction, strategy generation, and optimization.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from uuid import uuid4
from typing import Dict, Any, List

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../'))

from services.strategy.pattern_extractor import PatternExtractor
from services.strategy.strategy_generator import StrategyGenerator
from services.strategy.strategy_repository import StrategyRepository
from services.strategy.learning_optimizer import LearningOptimizer
from services.strategy_evolver import StrategyEvolver
from memory.models import Episode, Strategy
from memory.agent_memory_store import AgentMemoryStore
from memory.knowledge_store import KnowledgeStore
from config.feature_flags import FeatureFlags

class TestPatternExtractor:
    """Test PatternExtractor functionality"""
    
    @pytest.fixture
    def mock_memory_store(self):
        """Mock memory store for testing"""
        memory_store = Mock(spec=AgentMemoryStore)
        memory_store._pool = Mock()
        return memory_store
    
    @pytest.fixture
    def pattern_extractor(self, mock_memory_store):
        """Create PatternExtractor instance for testing"""
        return PatternExtractor(mock_memory_store)
    
    @pytest.mark.asyncio
    async def test_extract_patterns_insufficient_episodes(self, pattern_extractor, mock_memory_store):
        """Test pattern extraction with insufficient successful episodes"""
        # Mock database query to return empty results
        mock_connection = AsyncMock()
        mock_connection.fetch.return_value = []
        mock_memory_store._pool.acquire().__aenter__.return_value = mock_connection
        
        patterns = await pattern_extractor.extract_patterns_from_successful_episodes(
            project_id="test-project",
            days_back=30,
            min_episodes=5
        )
        
        assert patterns == []
    
    @pytest.mark.asyncio
    async def test_extract_context_patterns(self, pattern_extractor, mock_memory_store):
        """Test context pattern extraction"""
        # Create mock successful episodes
        mock_episodes = [
            Episode(
                episode_id=uuid4(),
                project_id="test-project",
                timestamp=datetime.utcnow(),
                perception={
                    "project_context": {
                        "team_size": 3,
                        "complexity": 0.6,
                        "resource_availability": 0.8
                    }
                },
                reasoning={"analysis": "test"},
                action={"task_adjustments": [{"type": "increase", "amount": 2}]},
                outcome={"success": True},
                outcome_quality=0.9,
                agent_version="2.0.0",
                control_mode="intelligence_enhanced",
                decision_source="hybrid"
            )
            for _ in range(6)  # Create 6 similar episodes
        ]
        
        # Mock the _get_successful_episodes method
        with patch.object(pattern_extractor, '_get_successful_episodes', return_value=mock_episodes):
            patterns = await pattern_extractor.extract_patterns_from_successful_episodes(
                project_id="test-project",
                days_back=30,
                min_episodes=5
            )
        
        assert len(patterns) >= 1
        context_patterns = [p for p in patterns if p.get('pattern_type') == 'context_pattern']
        assert len(context_patterns) >= 1
        
        # Verify pattern structure
        pattern = context_patterns[0]
        assert 'pattern_id' in pattern
        assert 'description' in pattern
        assert 'confidence' in pattern
        assert 'frequency' in pattern
        assert pattern['frequency'] == 6  # All 6 episodes matched

class TestStrategyGenerator:
    """Test StrategyGenerator functionality"""
    
    @pytest.fixture
    def mock_pattern_extractor(self):
        return Mock(spec=PatternExtractor)
    
    @pytest.fixture
    def mock_strategy_repository(self):
        return Mock(spec=StrategyRepository)
    
    @pytest.fixture
    def strategy_generator(self, mock_pattern_extractor, mock_strategy_repository):
        return StrategyGenerator(mock_pattern_extractor, mock_strategy_repository)
    
    @pytest.mark.asyncio
    async def test_generate_strategies_from_patterns(self, strategy_generator, mock_strategy_repository):
        """Test strategy generation from patterns"""
        # Mock pattern data
        mock_patterns = [
            {
                'pattern_type': 'context_pattern',
                'pattern_id': 'context_small_team_medium_complexity',
                'confidence': 0.8,
                'frequency': 5,
                'average_outcome_quality': 0.85,
                'context_signature': 'small_team_medium_complexity',
                'common_decisions': {
                    'task_adjustments': {
                        'frequency': 5,
                        'pattern_strength': 0.8,
                        'sample_decisions': [{'type': 'increase', 'amount': 1}]
                    }
                },
                'applicability_conditions': {
                    'team_size': {'min': 2, 'max': 4},
                    'complexity': {'min': 0.4, 'max': 0.8}
                }
            }
        ]
        
        # Mock strategy creation
        mock_strategy_repository.create_strategy = AsyncMock(return_value=uuid4())
        
        generated_ids = await strategy_generator.generate_strategies_from_patterns(
            patterns=mock_patterns
        )
        
        assert len(generated_ids) == 1
        mock_strategy_repository.create_strategy.assert_called_once()
    
    def test_calculate_strategy_confidence(self, strategy_generator):
        """Test strategy confidence calculation"""
        pattern = {
            'frequency': 8,
            'average_outcome_quality': 0.85,
            'confidence': 0.8,
            'supporting_episodes': [str(uuid4()) for _ in range(10)]
        }
        
        strategy_content = {
            'confidence_factors': {
                'pattern_frequency_score': 0.8,
                'outcome_quality_score': 0.85,
                'consistency_score': 0.8,
                'evidence_strength_score': 0.5
            }
        }
        
        confidence = strategy_generator._calculate_strategy_confidence(pattern, strategy_content)
        
        assert 0.0 <= confidence <= 1.0
        assert confidence > 0.7  # Should be high given good pattern data

class TestStrategyRepository:
    """Test StrategyRepository functionality"""
    
    @pytest.fixture
    def mock_knowledge_store(self):
        knowledge_store = Mock(spec=KnowledgeStore)
        knowledge_store._pool = Mock()
        return knowledge_store
    
    @pytest.fixture
    def strategy_repository(self, mock_knowledge_store):
        return StrategyRepository(mock_knowledge_store)
    
    @pytest.mark.asyncio
    async def test_create_strategy(self, strategy_repository, mock_knowledge_store):
        """Test strategy creation"""
        pattern_data = {
            'strategy_type': 'context_based',
            'confidence_factors': {'test': 0.8},
            'applicability_conditions': {'team_size': {'min': 2, 'max': 5}}
        }
        
        mock_strategy_id = uuid4()
        mock_knowledge_store.store_strategy = AsyncMock(return_value=mock_strategy_id)
        
        result_id = await strategy_repository.create_strategy(
            pattern_data=pattern_data,
            confidence=0.8,
            description="Test strategy",
            created_by="test"
        )
        
        assert result_id == mock_strategy_id
        mock_knowledge_store.store_strategy.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_log_strategy_performance(self, strategy_repository, mock_knowledge_store):
        """Test strategy performance logging"""
        mock_connection = AsyncMock()
        mock_knowledge_store._pool.acquire().__aenter__.return_value = mock_connection
        
        await strategy_repository.log_strategy_performance(
            strategy_id=uuid4(),
            episode_id=uuid4(),
            project_id="test-project",
            predicted_outcome={"expected_quality": 0.8},
            actual_outcome={"actual_quality": 0.75},
            outcome_quality=0.75,
            strategy_confidence=0.8
        )
        
        mock_connection.execute.assert_called_once()

class TestLearningOptimizer:
    """Test LearningOptimizer functionality"""
    
    @pytest.fixture
    def mock_strategy_repository(self):
        return Mock(spec=StrategyRepository)
    
    @pytest.fixture
    def learning_optimizer(self, mock_strategy_repository):
        return LearningOptimizer(mock_strategy_repository)
    
    @pytest.mark.asyncio
    async def test_optimize_strategy_performance(self, learning_optimizer, mock_strategy_repository):
        """Test strategy performance optimization"""
        # Mock strategy
        mock_strategy = Mock()
        mock_strategy.knowledge_id = uuid4()
        mock_strategy.confidence = 0.6
        
        mock_strategy_repository.get_active_strategies = AsyncMock(return_value=[mock_strategy])
        
        # Mock performance analysis
        with patch.object(learning_optimizer, '_analyze_strategy_performance') as mock_analyze:
            mock_analyze.return_value = {
                'sufficient_data': True,
                'overall_assessment': 'good',
                'performance_metrics': {'avg_outcome_quality': 0.85},
                'trend_analysis': {'trend': 'stable'}
            }
            
            with patch.object(learning_optimizer, '_determine_optimization_action') as mock_action:
                mock_action.return_value = {'action': 'no_action'}
                
                results = await learning_optimizer.optimize_strategy_performance()
        
        assert 'strategies_analyzed' in results
        assert results['strategies_analyzed'] >= 1

class TestStrategyEvolver:
    """Test StrategyEvolver orchestrator functionality"""
    
    @pytest.fixture
    def mock_memory_store(self):
        return Mock(spec=AgentMemoryStore)
    
    @pytest.fixture
    def mock_knowledge_store(self):
        return Mock(spec=KnowledgeStore)
    
    @pytest.fixture
    def mock_feature_flags(self):
        flags = Mock(spec=FeatureFlags)
        flags.enable_strategy_evolution = True
        return flags
    
    @pytest.fixture
    def strategy_evolver(self, mock_memory_store, mock_knowledge_store, mock_feature_flags):
        return StrategyEvolver(mock_memory_store, mock_knowledge_store, mock_feature_flags)
    
    @pytest.mark.asyncio
    async def test_run_daily_evolution_disabled(self, strategy_evolver, mock_feature_flags):
        """Test daily evolution when disabled by feature flag"""
        mock_feature_flags.enable_strategy_evolution = False
        strategy_evolver.evolution_enabled = False
        
        results = await strategy_evolver.run_daily_evolution()
        
        assert results['status'] == 'disabled'
        assert results['reason'] == 'feature_flag_disabled'
    
    @pytest.mark.asyncio
    async def test_run_daily_evolution_success(self, strategy_evolver):
        """Test successful daily evolution"""
        # Mock all phases to succeed
        with patch.object(strategy_evolver, '_extract_patterns_phase') as mock_extract:
            mock_extract.return_value = {'success': True, 'patterns': [{'test': 'pattern'}]}
            
            with patch.object(strategy_evolver, '_generate_strategies_phase') as mock_generate:
                mock_generate.return_value = {'success': True, 'strategies_generated': 2}
                
                with patch.object(strategy_evolver, '_optimize_strategies_phase') as mock_optimize:
                    mock_optimize.return_value = {'success': True}
                    
                    with patch.object(strategy_evolver, '_cleanup_phase') as mock_cleanup:
                        mock_cleanup.return_value = {'success': True}
                        
                        results = await strategy_evolver.run_daily_evolution()
        
        assert results['status'] == 'completed'
        assert 'phases' in results
        assert len(results['phases']) == 4
    
    @pytest.mark.asyncio
    async def test_health_check(self, strategy_evolver, mock_memory_store, mock_knowledge_store):
        """Test health check functionality"""
        mock_memory_store.health_check = AsyncMock(return_value={'status': 'ok'})
        mock_knowledge_store.health_check = AsyncMock(return_value=True)
        
        health_status = await strategy_evolver.health_check()
        
        assert 'overall_status' in health_status
        assert 'components' in health_status
        assert 'memory_store' in health_status['components']
        assert 'knowledge_store' in health_status['components']

# Integration test
class TestStrategyEvolutionIntegration:
    """Integration tests for the complete strategy evolution pipeline"""
    
    @pytest.mark.asyncio
    async def test_end_to_end_evolution_pipeline(self):
        """Test the complete evolution pipeline with mocked components"""
        # This is a placeholder for a more comprehensive integration test
        # In a real environment, this would test the full pipeline with actual data
        
        # Mock all components
        mock_memory_store = Mock(spec=AgentMemoryStore)
        mock_knowledge_store = Mock(spec=KnowledgeStore)
        mock_feature_flags = Mock(spec=FeatureFlags)
        mock_feature_flags.enable_strategy_evolution = True
        
        # Create evolver
        evolver = StrategyEvolver(mock_memory_store, mock_knowledge_store, mock_feature_flags)
        
        # Mock successful evolution
        with patch.object(evolver, 'run_daily_evolution') as mock_evolution:
            mock_evolution.return_value = {
                'status': 'completed',
                'summary': {
                    'patterns_extracted': 5,
                    'strategies_generated': 3,
                    'strategies_optimized': 2,
                    'strategies_deactivated': 1
                }
            }
            
            results = await evolver.run_daily_evolution()
        
        assert results['status'] == 'completed'
        assert results['summary']['patterns_extracted'] == 5

if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v'])