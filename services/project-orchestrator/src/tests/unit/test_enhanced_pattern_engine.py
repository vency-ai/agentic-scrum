"""
Unit tests for Enhanced Pattern Engine with Episode Integration
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from uuid import uuid4

from intelligence.pattern_engine import PatternEngine
from intelligence.pattern_combiner import PatternCombinationResult, CombinedPattern
from model_package.decision_context import EpisodeBasedDecisionContext, DecisionPattern
from models import ProjectData, PatternAnalysis, SimilarProject, SuccessIndicators

@pytest.fixture
def mock_chronicle_client():
    """Create mock Chronicle analytics client"""
    client = Mock()
    client.get_similar_projects = AsyncMock(return_value=[
        {
            "project_id": "PROJ-001",
            "similarity_score": 0.8,
            "team_size": 5,
            "completion_rate": 0.85,
            "avg_sprint_duration": 2.0,
            "optimal_task_count": 7,
            "key_success_factors": ["good_planning"]
        }
    ])
    client.get_project_retrospectives = AsyncMock(return_value=[])
    client.get_velocity_trends = AsyncMock(return_value=None)
    return client

@pytest.fixture
def mock_decision_config():
    """Create mock decision config"""
    config = Mock()
    config.min_velocity_confidence_for_scoring = 0.5
    return config

@pytest.fixture
def enhanced_pattern_engine(mock_chronicle_client, mock_decision_config):
    """Create Enhanced Pattern Engine instance"""
    return PatternEngine(
        chronicle_analytics_client=mock_chronicle_client,
        decision_config=mock_decision_config
    )

@pytest.fixture
def sample_project_data():
    """Create sample project data"""
    return ProjectData(
        project_id="TEST-001",
        backlog_tasks=15,
        unassigned_tasks=8,
        active_sprints=1,
        team_size=5,
        team_availability={"available_hours": 40},
        avg_task_complexity=0.7,
        domain_category="web_development",
        project_duration=8.0
    )

@pytest.fixture
def sample_episode_context():
    """Create sample episode context"""
    return EpisodeBasedDecisionContext(
        similar_episodes_analyzed=3,
        episodes_used_for_context=2,
        average_episode_similarity=0.82,
        context_quality_score=0.78,
        overall_recommendation_confidence=0.75,
        pattern_confidence_weight=0.6,
        identified_patterns=[
            DecisionPattern(
                pattern_type="task_count",
                pattern_value=6,
                success_rate=0.88,
                episode_count=2,
                confidence=0.8
            ),
            DecisionPattern(
                pattern_type="sprint_duration", 
                pattern_value=2,
                success_rate=0.92,
                episode_count=2,
                confidence=0.85
            )
        ],
        key_insights=[
            "6 tasks achieved 88% success in similar contexts",
            "2-week sprints optimal for team size 5"
        ],
        success_factors=["Balanced workload", "Clear requirements"],
        risk_factors=[],
        contributing_episodes=[],
        processing_duration_ms=42.5
    )

class TestEnhancedPatternEngine:
    """Test Enhanced Pattern Engine with episode integration"""
    
    def test_initialization(self, enhanced_pattern_engine):
        """Test Enhanced Pattern Engine initialization"""
        assert enhanced_pattern_engine.pattern_combiner is not None
        assert enhanced_pattern_engine.pattern_combiner.episode_weight_base == 0.4
        assert enhanced_pattern_engine.pattern_combiner.chronicle_weight_base == 0.6
    
    @pytest.mark.asyncio
    async def test_analyze_hybrid_patterns_with_episodes(
        self, 
        enhanced_pattern_engine, 
        sample_project_data, 
        sample_episode_context
    ):
        """Test hybrid pattern analysis with episode context"""
        enhanced_analysis, combination_result = await enhanced_pattern_engine.analyze_hybrid_patterns(
            project_id="TEST-001",
            project_data=sample_project_data,
            episode_context=sample_episode_context
        )
        
        # Should return enhanced analysis
        assert isinstance(enhanced_analysis, PatternAnalysis)
        assert isinstance(combination_result, PatternCombinationResult)
        
        # Should have episode integration metadata
        assert "episode_integration" in enhanced_analysis.performance_metrics
        episode_metadata = enhanced_analysis.performance_metrics["episode_integration"]
        assert episode_metadata["episodes_used"] == 2
        assert episode_metadata["episode_similarity"] == 0.82
    
    @pytest.mark.asyncio
    async def test_analyze_hybrid_patterns_without_episodes(
        self,
        enhanced_pattern_engine,
        sample_project_data
    ):
        """Test hybrid pattern analysis without episode context"""
        enhanced_analysis, combination_result = await enhanced_pattern_engine.analyze_hybrid_patterns(
            project_id="TEST-001",
            project_data=sample_project_data,
            episode_context=None
        )
        
        # Should return Chronicle-only analysis
        assert isinstance(enhanced_analysis, PatternAnalysis)
        assert combination_result is None
        
        # Should not have episode integration metadata
        assert "episode_integration" not in enhanced_analysis.performance_metrics
    
    @pytest.mark.asyncio
    async def test_enhance_chronicle_analysis_with_episodes(
        self,
        enhanced_pattern_engine,
        sample_project_data,
        sample_episode_context
    ):
        """Test enhancement of Chronicle analysis with episode data"""
        enhanced_analysis, combination_result = await enhanced_pattern_engine.analyze_hybrid_patterns(
            project_id="TEST-001",
            project_data=sample_project_data,
            episode_context=sample_episode_context
        )
        
        # Should have enhanced success indicators
        if enhanced_analysis.success_indicators:
            # Task count might be influenced by episode patterns
            assert enhanced_analysis.success_indicators.optimal_tasks_per_sprint > 0
            assert enhanced_analysis.success_indicators.recommended_sprint_duration > 0
            
        # Should have combination metadata
        assert combination_result is not None
        assert len(combination_result.combined_patterns) >= 0
    
    def test_generate_hybrid_insights_summary(
        self,
        enhanced_pattern_engine,
        sample_episode_context
    ):
        """Test hybrid insights summary generation"""
        # Create mock enhanced analysis
        mock_analysis = PatternAnalysis(
            similar_projects=[
                SimilarProject(
                    project_id="PROJ-001",
                    similarity_score=0.8,
                    team_size=5,
                    completion_rate=0.85,
                    avg_sprint_duration=2.0,
                    optimal_task_count=7,
                    key_success_factors=[]
                )
            ],
            velocity_trends=None,
            success_indicators=SuccessIndicators(
                optimal_tasks_per_sprint=6,
                recommended_sprint_duration=2,
                success_probability=0.85,
                risk_factors=[]
            ),
            performance_metrics={}
        )
        
        # Create mock combination result
        mock_combination = PatternCombinationResult(
            combined_patterns=[
                CombinedPattern(
                    pattern_type="task_count",
                    pattern_value=6,
                    success_rate=0.88,
                    confidence=0.8,
                    episode_source_weight=0.4,
                    chronicle_source_weight=0.6,
                    total_evidence_count=5,
                    source_breakdown={}
                )
            ],
            overall_confidence=0.78,
            pattern_source_influence={"episode": 0.4, "chronicle": 0.6},
            reasoning=["Combined analysis complete"],
            metadata={}
        )
        
        summary = enhanced_pattern_engine.generate_hybrid_insights_summary(
            enhanced_analysis=mock_analysis,
            combination_result=mock_combination,
            episode_context=sample_episode_context
        )
        
        # Should include episode memory information
        assert "episode memory" in summary.lower()
        assert "2 similar past decisions" in summary
        assert "82%" in summary  # Average similarity
        
        # Should include combined pattern information
        assert "combined" in summary.lower()
        
        # Should include episode insights
        assert any(insight in summary for insight in sample_episode_context.key_insights)
    
    def test_generate_hybrid_insights_summary_no_episodes(
        self,
        enhanced_pattern_engine
    ):
        """Test hybrid insights summary without episode data"""
        mock_analysis = PatternAnalysis(
            similar_projects=[],
            velocity_trends=None,
            success_indicators=None,
            performance_metrics={}
        )
        
        summary = enhanced_pattern_engine.generate_hybrid_insights_summary(
            enhanced_analysis=mock_analysis,
            combination_result=None,
            episode_context=None
        )
        
        # Should return basic Chronicle summary
        assert isinstance(summary, str)
        assert "episode" not in summary.lower()
    
    def test_validate_hybrid_pattern_confidence(
        self,
        enhanced_pattern_engine,
        sample_episode_context
    ):
        """Test hybrid pattern confidence validation"""
        # Create mock enhanced analysis
        mock_analysis = PatternAnalysis(
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
                recommended_sprint_duration=2,
                success_probability=0.85,
                risk_factors=[]
            ),
            performance_metrics={}
        )
        
        # Create mock combination result
        mock_combination = PatternCombinationResult(
            combined_patterns=[
                CombinedPattern(
                    pattern_type="task_count",
                    pattern_value=6,
                    success_rate=0.88,
                    confidence=0.8,
                    episode_source_weight=0.4,
                    chronicle_source_weight=0.6,
                    total_evidence_count=5,
                    source_breakdown={}
                )
            ],
            overall_confidence=0.75,
            pattern_source_influence={"episode": 0.4, "chronicle": 0.6},
            reasoning=["Hybrid analysis complete"],
            metadata={}
        )
        
        confidence = enhanced_pattern_engine.validate_hybrid_pattern_confidence(
            enhanced_analysis=mock_analysis,
            combination_result=mock_combination
        )
        
        # Should have enhanced confidence due to episode integration
        assert 0.0 <= confidence.score <= 1.0
        assert "episode memory integration" in confidence.reasoning.lower()
        assert "hybrid patterns" in confidence.reasoning.lower()
    
    def test_validate_hybrid_pattern_confidence_no_episodes(
        self,
        enhanced_pattern_engine
    ):
        """Test hybrid pattern confidence validation without episodes"""
        mock_analysis = PatternAnalysis(
            similar_projects=[],
            velocity_trends=None,
            success_indicators=None,
            performance_metrics={}
        )
        
        confidence = enhanced_pattern_engine.validate_hybrid_pattern_confidence(
            enhanced_analysis=mock_analysis,
            combination_result=None
        )
        
        # Should return base Chronicle confidence
        assert 0.0 <= confidence.score <= 1.0
        assert "episode" not in confidence.reasoning.lower()
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_with_episodes(
        self,
        enhanced_pattern_engine,
        sample_project_data,
        sample_episode_context
    ):
        """Test performance monitoring for hybrid analysis"""
        enhanced_analysis, combination_result = await enhanced_pattern_engine.analyze_hybrid_patterns(
            project_id="TEST-001",
            project_data=sample_project_data,
            episode_context=sample_episode_context
        )
        
        # Should have performance metrics for hybrid analysis
        performance_summary = enhanced_pattern_engine.get_performance_summary()
        assert isinstance(performance_summary, dict)
        
        # Should track hybrid analysis operations
        operation_names = [op.get("operation_name", "") for op in performance_summary.get("operations", [])]
        assert any("hybrid_pattern_analysis" in name for name in operation_names)
        assert any("pattern_combination" in name for name in operation_names)
    
    @pytest.mark.asyncio 
    async def test_error_handling_in_hybrid_analysis(
        self,
        enhanced_pattern_engine,
        sample_project_data
    ):
        """Test error handling in hybrid pattern analysis"""
        # Create malformed episode context
        malformed_episode = Mock()
        malformed_episode.episodes_used_for_context = "invalid"
        
        # Should handle gracefully
        enhanced_analysis, combination_result = await enhanced_pattern_engine.analyze_hybrid_patterns(
            project_id="TEST-001",
            project_data=sample_project_data,
            episode_context=malformed_episode
        )
        
        # Should still return valid analysis (Chronicle-only fallback)
        assert isinstance(enhanced_analysis, PatternAnalysis)
        
        # Combination result might be None or empty due to error
        if combination_result:
            assert len(combination_result.combined_patterns) == 0
    
    def test_pattern_combiner_integration(self, enhanced_pattern_engine):
        """Test Pattern Combiner integration"""
        # Verify Pattern Combiner is properly integrated
        assert hasattr(enhanced_pattern_engine, 'pattern_combiner')
        assert enhanced_pattern_engine.pattern_combiner is not None
        
        # Verify configuration
        combiner = enhanced_pattern_engine.pattern_combiner
        assert combiner.episode_weight_base == 0.4
        assert combiner.chronicle_weight_base == 0.6
        assert combiner.min_confidence_threshold == 0.3

if __name__ == "__main__":
    pytest.main([__file__, "-v"])