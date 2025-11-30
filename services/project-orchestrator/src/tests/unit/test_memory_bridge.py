"""
Unit tests for Memory Bridge Service
"""

import pytest
import asyncio
from uuid import UUID, uuid4
from datetime import datetime
from unittest.mock import Mock

from services.memory_bridge import MemoryBridge
from model_package.decision_context import EpisodeBasedDecisionContext, DecisionPattern
from memory.models import Episode

@pytest.fixture
def memory_bridge():
    """Create Memory Bridge instance for testing"""
    return MemoryBridge(
        min_episodes_for_patterns=2,
        min_similarity_threshold=0.6,
        quality_weight=0.3
    )

@pytest.fixture
def sample_episode_1():
    """Create sample episode with good outcome"""
    return Episode(
        episode_id=str(uuid4()),
        project_id="TEST-001",
        timestamp=datetime.utcnow(),
        perception={
            "team_size": 5,
            "backlog_tasks": 12,
            "technology_stack": ["Python", "React"]
        },
        reasoning={
            "decision_rationale": "Team can handle 6 tasks effectively"
        },
        action={
            "create_new_sprint": True,
            "tasks_to_assign": 6,
            "sprint_duration_weeks": 2
        },
        outcome_quality=0.92,
        similarity=0.85  # Added for testing
    )

@pytest.fixture
def sample_episode_2():
    """Create sample episode with moderate outcome"""
    return Episode(
        episode_id=str(uuid4()),
        project_id="TEST-002",
        timestamp=datetime.utcnow(),
        perception={
            "team_size": 4,
            "backlog_tasks": 10,
            "technology_stack": ["Python", "Vue"]
        },
        reasoning={
            "decision_rationale": "Smaller team, fewer tasks"
        },
        action={
            "create_new_sprint": True,
            "tasks_to_assign": 5,
            "sprint_duration_weeks": 2
        },
        outcome_quality=0.78,
        similarity=0.72
    )

@pytest.fixture
def sample_episode_3():
    """Create sample episode with poor outcome"""
    return Episode(
        episode_id=str(uuid4()),
        project_id="TEST-003",
        timestamp=datetime.utcnow(),
        perception={
            "team_size": 6,
            "backlog_tasks": 20,
            "technology_stack": ["Java", "Angular"]
        },
        reasoning={
            "decision_rationale": "Aggressive sprint planning"
        },
        action={
            "create_new_sprint": True,
            "tasks_to_assign": 12,
            "sprint_duration_weeks": 2
        },
        outcome_quality=0.45,
        similarity=0.65
    )

@pytest.fixture
def incomplete_episode():
    """Create episode with missing data"""
    return Episode(
        episode_id=str(uuid4()),
        project_id="INCOMPLETE-001",
        timestamp=datetime.utcnow(),
        perception={},  # Missing team_size
        reasoning={},  # Empty reasoning dict instead of None
        action={
            "create_new_sprint": True
        },
        outcome_quality=None,
        similarity=0.80
    )

@pytest.fixture
def current_project_context():
    """Sample current project context"""
    return {
        "project_id": "CURRENT-001",
        "team_size": 5,
        "backlog_tasks": 15,
        "technology_stack": ["Python", "React"],
        "active_sprint": None
    }

class TestMemoryBridge:
    """Test Memory Bridge functionality"""
    
    @pytest.mark.asyncio
    async def test_empty_episodes_list(self, memory_bridge, current_project_context):
        """Test handling of empty episodes list"""
        context = await memory_bridge.translate_episodes_to_context([], current_project_context)
        
        assert isinstance(context, EpisodeBasedDecisionContext)
        assert context.similar_episodes_analyzed == 0
        assert context.episodes_used_for_context == 0
        assert context.overall_recommendation_confidence == 0.0
        assert len(context.key_insights) == 0
        assert len(context.contributing_episodes) == 0
    
    @pytest.mark.asyncio
    async def test_single_quality_episode(self, memory_bridge, sample_episode_1, current_project_context):
        """Test processing single high-quality episode"""
        context = await memory_bridge.translate_episodes_to_context([sample_episode_1], current_project_context)
        
        assert context.similar_episodes_analyzed == 1
        assert context.episodes_used_for_context == 1
        assert context.average_episode_similarity == 0.85
        assert context.context_quality_score > 0.7
        assert len(context.contributing_episodes) == 1
        assert context.contributing_episodes[0].episode_id == sample_episode_1.episode_id
        assert context.contributing_episodes[0].outcome_quality == 0.92
    
    @pytest.mark.asyncio
    async def test_multiple_episodes_pattern_detection(
        self, 
        memory_bridge, 
        sample_episode_1, 
        sample_episode_2, 
        current_project_context
    ):
        """Test pattern detection across multiple episodes"""
        episodes = [sample_episode_1, sample_episode_2]
        context = await memory_bridge.translate_episodes_to_context(episodes, current_project_context)
        
        assert context.similar_episodes_analyzed == 2
        assert context.episodes_used_for_context == 2
        assert len(context.identified_patterns) >= 1
        
        # Check for task count pattern
        task_patterns = [p for p in context.identified_patterns if p.pattern_type == "task_count"]
        assert len(task_patterns) == 1
        
        task_pattern = task_patterns[0]
        assert task_pattern.pattern_value in [5, 6]  # Should pick the better performing option
        assert task_pattern.success_rate > 0.7
        assert task_pattern.episode_count >= 1
    
    @pytest.mark.asyncio
    async def test_episode_filtering(
        self, 
        memory_bridge, 
        sample_episode_1, 
        sample_episode_3, 
        incomplete_episode, 
        current_project_context
    ):
        """Test filtering of episodes by quality and completeness"""
        episodes = [sample_episode_1, sample_episode_3, incomplete_episode]
        context = await memory_bridge.translate_episodes_to_context(episodes, current_project_context)
        
        # Should filter out incomplete episode and low-quality episode
        assert context.similar_episodes_analyzed == 3
        assert context.episodes_used_for_context <= 2  # Filtered down
        
        # Check that incomplete episode was filtered out
        episode_ids = [ep.episode_id for ep in context.contributing_episodes]
        assert sample_episode_1.episode_id in episode_ids
        assert incomplete_episode.episode_id not in episode_ids
    
    @pytest.mark.asyncio
    async def test_success_rate_calculation(
        self, 
        memory_bridge, 
        sample_episode_1, 
        sample_episode_2, 
        current_project_context
    ):
        """Test success rate calculation from episodes"""
        episodes = [sample_episode_1, sample_episode_2]
        context = await memory_bridge.translate_episodes_to_context(episodes, current_project_context)
        
        # Should calculate average success rate
        expected_avg = (0.92 + 0.78) / 2  # 0.85
        assert context.average_success_rate is not None
        assert abs(context.average_success_rate - expected_avg) < 0.01
        assert context.success_rate_confidence > 0.5
    
    @pytest.mark.asyncio
    async def test_key_insights_generation(
        self, 
        memory_bridge, 
        sample_episode_1, 
        sample_episode_2, 
        current_project_context
    ):
        """Test generation of human-readable insights"""
        episodes = [sample_episode_1, sample_episode_2]
        context = await memory_bridge.translate_episodes_to_context(episodes, current_project_context)
        
        assert len(context.key_insights) > 0
        assert len(context.success_factors) >= 0
        
        # Check insight content
        insights_text = " ".join(context.key_insights)
        assert "success rate" in insights_text.lower()
        assert "episodes" in insights_text.lower()
    
    @pytest.mark.asyncio
    async def test_recommendations_generation(
        self, 
        memory_bridge, 
        sample_episode_1, 
        sample_episode_2, 
        current_project_context
    ):
        """Test generation of specific recommendations"""
        episodes = [sample_episode_1, sample_episode_2]
        context = await memory_bridge.translate_episodes_to_context(episodes, current_project_context)
        
        # Should generate task count recommendation
        assert context.recommended_task_count is not None
        assert context.recommended_task_count in [5, 6]  # Based on sample episodes
        
        # Should generate sprint duration recommendation
        assert context.recommended_sprint_duration_weeks is not None
        assert context.recommended_sprint_duration_weeks == 2
    
    @pytest.mark.asyncio
    async def test_confidence_calculation(
        self, 
        memory_bridge, 
        sample_episode_1, 
        sample_episode_2, 
        current_project_context
    ):
        """Test confidence calculation"""
        episodes = [sample_episode_1, sample_episode_2]
        context = await memory_bridge.translate_episodes_to_context(episodes, current_project_context)
        
        assert 0.0 <= context.overall_recommendation_confidence <= 1.0
        assert 0.0 <= context.pattern_confidence_weight <= 1.0
        
        # With good episodes, confidence should be reasonable
        assert context.overall_recommendation_confidence > 0.4
    
    @pytest.mark.asyncio
    async def test_processing_duration_tracking(
        self, 
        memory_bridge, 
        sample_episode_1, 
        current_project_context
    ):
        """Test that processing duration is tracked"""
        context = await memory_bridge.translate_episodes_to_context([sample_episode_1], current_project_context)
        
        assert context.processing_duration_ms is not None
        assert context.processing_duration_ms > 0.0
        assert context.processing_duration_ms < 1000.0  # Should be fast
    
    def test_filter_relevant_episodes(self, memory_bridge, sample_episode_1, incomplete_episode):
        """Test episode filtering logic"""
        episodes = [sample_episode_1, incomplete_episode]
        relevant = memory_bridge._filter_relevant_episodes(episodes)
        
        # Should filter out incomplete episode
        assert len(relevant) == 1
        assert relevant[0].episode_id == sample_episode_1.episode_id
    
    def test_is_episode_complete(self, memory_bridge, sample_episode_1, incomplete_episode):
        """Test episode completeness check"""
        assert memory_bridge._is_episode_complete(sample_episode_1) == True
        assert memory_bridge._is_episode_complete(incomplete_episode) == False
    
    def test_calculate_episode_confidence(self, memory_bridge, sample_episode_1):
        """Test individual episode confidence calculation"""
        confidence = memory_bridge._calculate_episode_confidence(sample_episode_1)
        
        assert 0.0 <= confidence <= 1.0
        # Should be high confidence for complete episode with good outcome
        assert confidence > 0.7
    
    def test_summarize_episode_decision(self, memory_bridge, sample_episode_1):
        """Test episode decision summarization"""
        summary = memory_bridge._summarize_episode_decision(sample_episode_1)
        
        assert isinstance(summary, str)
        assert len(summary) > 0
        assert "6 tasks" in summary  # Should mention task count
        assert "successfully" in summary.lower()  # Should mention success
    
    def test_extract_key_learning(self, memory_bridge, sample_episode_1, current_project_context):
        """Test key learning extraction"""
        learning = memory_bridge._extract_key_learning(sample_episode_1, current_project_context)
        
        assert isinstance(learning, str)
        assert len(learning) > 0
        assert "team size" in learning.lower() or "tasks" in learning.lower()

if __name__ == "__main__":
    pytest.main([__file__, "-v"])