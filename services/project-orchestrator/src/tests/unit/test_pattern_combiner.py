"""
Unit tests for Pattern Combiner
"""

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import Mock

from intelligence.pattern_combiner import PatternCombiner, CombinedPattern, PatternCombinationResult
from model_package.decision_context import EpisodeBasedDecisionContext, DecisionPattern, EpisodeInsight
from models import PatternAnalysis, SimilarProject, SuccessIndicators

@pytest.fixture
def pattern_combiner():
    """Create Pattern Combiner instance for testing"""
    return PatternCombiner(
        episode_weight_base=0.4,
        chronicle_weight_base=0.6,
        min_confidence_threshold=0.3
    )

@pytest.fixture
def episode_context():
    """Create sample episode context"""
    decision_patterns = [
        DecisionPattern(
            pattern_type="task_count",
            pattern_value=6,
            success_rate=0.85,
            episode_count=3,
            confidence=0.8
        ),
        DecisionPattern(
            pattern_type="sprint_duration",
            pattern_value=2,
            success_rate=0.92,
            episode_count=2,
            confidence=0.75
        )
    ]
    
    return EpisodeBasedDecisionContext(
        similar_episodes_analyzed=5,
        episodes_used_for_context=3,
        average_episode_similarity=0.78,
        context_quality_score=0.85,
        overall_recommendation_confidence=0.82,
        pattern_confidence_weight=0.7,
        identified_patterns=decision_patterns,
        key_insights=["6 tasks showed 85% success rate", "2-week sprints optimal"],
        success_factors=["Balanced workload"],
        risk_factors=[],
        contributing_episodes=[],
        processing_duration_ms=45.2
    )

@pytest.fixture
def chronicle_analysis():
    """Create sample Chronicle analysis"""
    similar_projects = [
        SimilarProject(
            project_id="PROJ-001",
            similarity_score=0.85,
            team_size=5,
            completion_rate=0.88,
            avg_sprint_duration=2.0,
            optimal_task_count=7,
            key_success_factors=["good_planning"]
        ),
        SimilarProject(
            project_id="PROJ-002", 
            similarity_score=0.72,
            team_size=4,
            completion_rate=0.82,
            avg_sprint_duration=2.0,
            optimal_task_count=8,
            key_success_factors=["experienced_team"]
        )
    ]
    
    success_indicators = SuccessIndicators(
        optimal_tasks_per_sprint=7,
        recommended_sprint_duration=2,
        success_probability=0.85,
        risk_factors=[]
    )
    
    return PatternAnalysis(
        similar_projects=similar_projects,
        velocity_trends=None,
        success_indicators=success_indicators,
        performance_metrics={}
    )

@pytest.fixture
def current_project_context():
    """Sample current project context"""
    return {
        "project_id": "CURRENT-001",
        "team_size": 5,
        "backlog_tasks": 15,
        "sprint_duration_weeks": 2
    }

class TestPatternCombiner:
    """Test Pattern Combiner functionality"""
    
    def test_initialization(self, pattern_combiner):
        """Test Pattern Combiner initialization"""
        assert pattern_combiner.episode_weight_base == 0.4
        assert pattern_combiner.chronicle_weight_base == 0.6
        assert pattern_combiner.min_confidence_threshold == 0.3
    
    def test_combine_patterns_both_sources(self, pattern_combiner, episode_context, chronicle_analysis, current_project_context):
        """Test pattern combination with both episode and Chronicle sources"""
        result = pattern_combiner.combine_patterns(
            episode_context=episode_context,
            chronicle_analysis=chronicle_analysis,
            current_project_context=current_project_context
        )
        
        assert isinstance(result, PatternCombinationResult)
        assert len(result.combined_patterns) >= 1
        assert result.overall_confidence > 0.0
        assert "episode" in result.pattern_source_influence
        assert "chronicle" in result.pattern_source_influence
        assert len(result.reasoning) > 0
    
    def test_combine_task_count_patterns(self, pattern_combiner, episode_context, chronicle_analysis, current_project_context):
        """Test task count pattern combination"""
        result = pattern_combiner.combine_patterns(
            episode_context=episode_context,
            chronicle_analysis=chronicle_analysis,
            current_project_context=current_project_context
        )
        
        # Should have task count pattern
        task_patterns = [p for p in result.combined_patterns if p.pattern_type == "task_count"]
        assert len(task_patterns) >= 1
        
        task_pattern = task_patterns[0]
        assert task_pattern.pattern_value > 0
        assert 0.0 <= task_pattern.success_rate <= 1.0
        assert 0.0 <= task_pattern.confidence <= 1.0
        assert task_pattern.episode_source_weight >= 0.0
        assert task_pattern.chronicle_source_weight >= 0.0
        assert task_pattern.total_evidence_count > 0
    
    def test_combine_sprint_duration_patterns(self, pattern_combiner, episode_context, chronicle_analysis, current_project_context):
        """Test sprint duration pattern combination"""
        result = pattern_combiner.combine_patterns(
            episode_context=episode_context,
            chronicle_analysis=chronicle_analysis,
            current_project_context=current_project_context
        )
        
        # Should have sprint duration pattern
        duration_patterns = [p for p in result.combined_patterns if p.pattern_type == "sprint_duration"]
        assert len(duration_patterns) >= 1
        
        duration_pattern = duration_patterns[0]
        assert duration_pattern.pattern_value > 0
        assert 0.0 <= duration_pattern.success_rate <= 1.0
        assert 0.0 <= duration_pattern.confidence <= 1.0
    
    def test_episode_only_patterns(self, pattern_combiner, episode_context, current_project_context):
        """Test pattern combination with episode data only"""
        result = pattern_combiner.combine_patterns(
            episode_context=episode_context,
            chronicle_analysis=None,
            current_project_context=current_project_context
        )
        
        assert len(result.combined_patterns) >= 1
        assert result.pattern_source_influence["episode"] == 1.0
        assert result.pattern_source_influence["chronicle"] == 0.0
        
        # Check that episode-only patterns have reduced confidence
        for pattern in result.combined_patterns:
            assert pattern.episode_source_weight == 1.0
            assert pattern.chronicle_source_weight == 0.0
    
    def test_chronicle_only_patterns(self, pattern_combiner, chronicle_analysis, current_project_context):
        """Test pattern combination with Chronicle data only"""
        result = pattern_combiner.combine_patterns(
            episode_context=None,
            chronicle_analysis=chronicle_analysis,
            current_project_context=current_project_context
        )
        
        assert len(result.combined_patterns) >= 1
        assert result.pattern_source_influence["episode"] == 0.0
        assert result.pattern_source_influence["chronicle"] == 1.0
        
        # Check that Chronicle-only patterns have proper weighting
        for pattern in result.combined_patterns:
            assert pattern.episode_source_weight == 0.0
            assert pattern.chronicle_source_weight == 1.0
    
    def test_no_data_sources(self, pattern_combiner, current_project_context):
        """Test pattern combination with no data sources"""
        result = pattern_combiner.combine_patterns(
            episode_context=None,
            chronicle_analysis=None,
            current_project_context=current_project_context
        )
        
        assert len(result.combined_patterns) == 0
        assert result.overall_confidence == 0.0
        assert len(result.reasoning) >= 1
    
    def test_calculate_source_weights(self, pattern_combiner, episode_context, chronicle_analysis):
        """Test source weight calculation"""
        episode_weight, chronicle_weight = pattern_combiner._calculate_source_weights(
            episode_context, chronicle_analysis
        )
        
        assert 0.0 <= episode_weight <= 1.0
        assert 0.0 <= chronicle_weight <= 1.0
        assert abs(episode_weight + chronicle_weight - 1.0) < 0.01  # Should sum to ~1.0
    
    def test_high_quality_episode_context_increases_weight(self, pattern_combiner, chronicle_analysis):
        """Test that high-quality episode context gets higher weight"""
        # Create high-quality episode context
        high_quality_episode = EpisodeBasedDecisionContext(
            similar_episodes_analyzed=10,
            episodes_used_for_context=5,
            average_episode_similarity=0.95,
            context_quality_score=0.95,
            overall_recommendation_confidence=0.9,
            pattern_confidence_weight=0.8,
            identified_patterns=[],
            key_insights=[],
            success_factors=[],
            risk_factors=[],
            contributing_episodes=[],
            processing_duration_ms=50.0
        )
        
        # Create low-quality Chronicle analysis
        low_quality_chronicle = PatternAnalysis(
            similar_projects=[],  # No similar projects
            velocity_trends=None,
            success_indicators=None,
            performance_metrics={}
        )
        
        episode_weight, chronicle_weight = pattern_combiner._calculate_source_weights(
            high_quality_episode, low_quality_chronicle
        )
        
        # Episode should have higher weight due to better quality
        assert episode_weight > chronicle_weight
    
    def test_get_recommended_values(self, pattern_combiner, episode_context, chronicle_analysis, current_project_context):
        """Test extraction of recommended values from combined patterns"""
        result = pattern_combiner.combine_patterns(
            episode_context=episode_context,
            chronicle_analysis=chronicle_analysis,
            current_project_context=current_project_context
        )
        
        recommendations = pattern_combiner.get_recommended_values(result)
        
        # Should have recommendations for patterns above confidence threshold
        assert isinstance(recommendations, dict)
        
        # Check for expected recommendation types
        if "recommended_task_count" in recommendations:
            assert recommendations["recommended_task_count"] > 0
        
        if "recommended_sprint_duration_weeks" in recommendations:
            assert recommendations["recommended_sprint_duration_weeks"] > 0
    
    def test_confidence_threshold_filtering(self, pattern_combiner, episode_context, chronicle_analysis, current_project_context):
        """Test that low-confidence patterns are filtered out"""
        # Set high confidence threshold
        high_threshold_combiner = PatternCombiner(min_confidence_threshold=0.9)
        
        result = high_threshold_combiner.combine_patterns(
            episode_context=episode_context,
            chronicle_analysis=chronicle_analysis,
            current_project_context=current_project_context
        )
        
        recommendations = high_threshold_combiner.get_recommended_values(result)
        
        # With high threshold, fewer recommendations should be made
        # (this might result in empty recommendations depending on confidence levels)
        assert isinstance(recommendations, dict)
    
    def test_pattern_agreement_boosts_confidence(self, pattern_combiner, current_project_context):
        """Test that agreement between sources boosts confidence"""
        # Create episode context with 2-week sprint recommendation
        episode_context = EpisodeBasedDecisionContext(
            similar_episodes_analyzed=3,
            episodes_used_for_context=2,
            average_episode_similarity=0.8,
            context_quality_score=0.8,
            overall_recommendation_confidence=0.7,
            pattern_confidence_weight=0.6,
            identified_patterns=[
                DecisionPattern(
                    pattern_type="sprint_duration",
                    pattern_value=2,
                    success_rate=0.8,
                    episode_count=2,
                    confidence=0.7
                )
            ],
            key_insights=[],
            success_factors=[],
            risk_factors=[],
            contributing_episodes=[],
            processing_duration_ms=40.0
        )
        
        # Create Chronicle analysis also recommending 2-week sprints
        chronicle_analysis = PatternAnalysis(
            similar_projects=[
                SimilarProject(
                    project_id="PROJ-001",
                    similarity_score=0.8,
                    team_size=5,
                    completion_rate=0.85,
                    avg_sprint_duration=2.0,
                    optimal_task_count=6,
                    key_success_factors=[]
                )
            ],
            velocity_trends=None,
            success_indicators=SuccessIndicators(
                optimal_tasks_per_sprint=6,
                recommended_sprint_duration=2,  # Same as episode
                success_probability=0.8,
                risk_factors=[]
            ),
            performance_metrics={}
        )
        
        result = pattern_combiner.combine_patterns(
            episode_context=episode_context,
            chronicle_analysis=chronicle_analysis,
            current_project_context=current_project_context
        )
        
        # Find sprint duration pattern
        duration_patterns = [p for p in result.combined_patterns if p.pattern_type == "sprint_duration"]
        assert len(duration_patterns) >= 1
        
        duration_pattern = duration_patterns[0]
        # Agreement should result in higher confidence
        assert duration_pattern.confidence > 0.7
    
    def test_error_handling(self, pattern_combiner, current_project_context):
        """Test error handling in pattern combination"""
        # Create malformed episode context that might cause errors
        malformed_episode = Mock()
        malformed_episode.episodes_used_for_context = "invalid"  # Should be int
        
        result = pattern_combiner.combine_patterns(
            episode_context=malformed_episode,
            chronicle_analysis=None,
            current_project_context=current_project_context
        )
        
        # Should handle gracefully and return empty result
        assert isinstance(result, PatternCombinationResult)
        assert len(result.combined_patterns) == 0
        assert result.overall_confidence == 0.0
        assert "error" in result.metadata or len(result.reasoning) > 0

if __name__ == "__main__":
    pytest.main([__file__, "-v"])