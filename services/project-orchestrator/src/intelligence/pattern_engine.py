from typing import Dict, Any, List, Optional, Tuple
import structlog
import time # New import

from models import (
    ProjectData,
    PatternAnalysis,
    ConfidenceScore,
    SimilarProject,
    VelocityTrends,
    SuccessIndicators,
    ProjectCharacteristics
)
from model_package.decision_context import EpisodeBasedDecisionContext
from .similarity_analyzer import find_similar_projects, extract_project_characteristics
from .velocity_analyzer import analyze_velocity_trends
from .success_detector import identify_success_patterns
from .pattern_cache import pattern_cache # Import the global pattern_cache instance
from .performance_monitor import PerformanceMonitor, PerformanceMetrics # Modified import
from .pattern_combiner import PatternCombiner, PatternCombinationResult

logger = structlog.get_logger()

class PatternEngine:
    def __init__(self, chronicle_analytics_client: Any, decision_config: Any, performance_monitor: Optional[PerformanceMonitor] = None, strategy_repository=None):
        self.chronicle_analytics_client = chronicle_analytics_client
        self.decision_config = decision_config # Store decision_config
        self.performance_monitor = performance_monitor if performance_monitor else PerformanceMonitor() # Use provided monitor or create new
        self.strategy_repository = strategy_repository  # Strategy repository for Strategy Evolution Layer
        
        # Initialize Pattern Combiner for hybrid intelligence
        self.pattern_combiner = PatternCombiner(
            episode_weight_base=0.4,
            chronicle_weight_base=0.6,
            min_confidence_threshold=0.3
        )

    async def analyze_project_patterns(self, project_id: str, project_data: ProjectData) -> PatternAnalysis:
        """Coordinates various pattern analysis components to generate a comprehensive analysis."""
        logger.info("Starting project pattern analysis", project_id=project_id)

        with self.performance_monitor.time_operation("full_pattern_analysis"):
            # Try to retrieve from cache first
            cached_analysis = pattern_cache.get(f"pattern_analysis_{project_id}")
            if cached_analysis:
                logger.info("Returning cached pattern analysis", project_id=project_id)
                self.performance_monitor.record_cache_hit()
                return PatternAnalysis(**cached_analysis) # Reconstruct Pydantic model from cached dict

            # Record cache miss for performance tracking
            self.performance_monitor.record_cache_miss()
            
            # 1. Retrieve historical data from Chronicle Service
            # Use the actual similar projects endpoint instead of dummy data
            similar_projects_raw = await self.chronicle_analytics_client.get_similar_projects(project_id, similarity_threshold=0.7)
            project_retrospectives = await self.chronicle_analytics_client.get_project_retrospectives(project_id)
            logger.debug("[PATTERN_ENGINE] Retrieved project retrospectives", project_id=project_id, retrospectives=project_retrospectives)

            # Process project's own retrospectives for optimal task count
            own_optimal_task_counts = [r.get("optimal_task_count") for r in project_retrospectives if r.get("optimal_task_count") is not None]
            if own_optimal_task_counts:
                avg_own_optimal_task_count = round(sum(own_optimal_task_counts) / len(own_optimal_task_counts))
                # Add a self-referencing similar project with high confidence
                similar_projects_raw.append({
                    "project_id": project_id,
                    "similarity_score": 1.0, # Self-similarity is 1.0
                    "team_size": project_data.team_size,
                    "completion_rate": 1.0, # Assume high completion for optimal task count
                    "avg_sprint_duration": project_data.sprint_duration_weeks, # Use current project's duration
                    "optimal_task_count": avg_own_optimal_task_count,
                    "key_success_factors": ["self_historical_data"]
                })

            # 2. Project Similarity Analysis
            similar_projects: List[SimilarProject] = []
            with self.performance_monitor.time_operation("similarity_analysis"):
                if similar_projects_raw:
                    # Convert the raw data from Chronicle Service to SimilarProject models
                    for proj_data in similar_projects_raw:
                        similar_projects.append(SimilarProject(
                            project_id=proj_data.get("project_id", ""),
                            similarity_score=proj_data.get("similarity_score", 0.0),
                            team_size=proj_data.get("team_size", 0),
                            completion_rate=proj_data.get("completion_rate", 0.0),
                            avg_sprint_duration=proj_data.get("avg_sprint_duration", 0.0),
                            optimal_task_count=proj_data.get("optimal_task_count"),
                            key_success_factors=proj_data.get("key_success_factors", [])
                        ))
            velocity_trends: Optional[VelocityTrends] = None
            with self.performance_monitor.time_operation("velocity_analysis"):
                chronicle_velocity_data = await self.chronicle_analytics_client.get_velocity_trends(project_id)
                if chronicle_velocity_data and chronicle_velocity_data.velocity_trend_data:
                    # Convert List[SprintSummary] to List[Dict[str, Any]] for analyze_velocity_trends
                    velocity_data_for_analyzer = [sprint.dict() for sprint in chronicle_velocity_data.velocity_trend_data]
                    velocity_trends = analyze_velocity_trends(velocity_data_for_analyzer)

            # 4. Success Pattern Detection
            success_indicators: Optional[SuccessIndicators] = None
            with self.performance_monitor.time_operation("success_pattern_detection"):
                if similar_projects:
                    success_indicators = identify_success_patterns(similar_projects)

            current_performance_summary = self.performance_monitor.get_summary() # Get summary before creating PatternAnalysis
            logger.debug("PatternEngine: Current performance summary before PatternAnalysis creation", summary=current_performance_summary)

            pattern_analysis = PatternAnalysis(
                similar_projects=similar_projects,
                velocity_trends=velocity_trends,
                success_indicators=success_indicators,
                performance_metrics=current_performance_summary # Assign performance metrics
            )
            
            logger.debug("PatternEngine: PatternAnalysis object before caching", pattern_analysis_dict=pattern_analysis.dict())

            # Cache the analysis result
            pattern_cache.set(f"pattern_analysis_{project_id}", pattern_analysis.dict())

            logger.info("Completed project pattern analysis", project_id=project_id)
            return pattern_analysis

    def get_performance_summary(self, operation_name: Optional[str] = None) -> Dict:
        return self.performance_monitor.get_summary(operation_name)

    def generate_insights_summary(self, pattern_analysis: PatternAnalysis) -> str:
        """Generates a human-readable summary of the pattern analysis insights."""
        summary_parts = []

        if pattern_analysis.similar_projects:
            summary_parts.append(f"Found {len(pattern_analysis.similar_projects)} similar projects.")
            # Add more details from similar projects if needed

        if pattern_analysis.velocity_trends:
            summary_parts.append(f"Team velocity trend is {pattern_analysis.velocity_trends.trend_direction} (current: {pattern_analysis.velocity_trends.current_team_velocity}).")

        if pattern_analysis.success_indicators:
            summary_parts.append(f"Based on similar projects, success probability is {pattern_analysis.success_indicators.success_probability*100:.0f}% with optimal {pattern_analysis.success_indicators.optimal_tasks_per_sprint} tasks per sprint and {pattern_analysis.success_indicators.recommended_sprint_duration}-week duration.")

        if not summary_parts:
            return "No significant patterns or insights identified from historical data."

        return " ".join(summary_parts)

    def validate_pattern_confidence(self, analysis: PatternAnalysis) -> ConfidenceScore:
        """Validates the confidence of the pattern analysis results."""
        # This is a simplified confidence calculation. A real system would use more factors.
        confidence_score = 0.0
        reasoning_parts = []

        if analysis.similar_projects:
            confidence_score += 0.3 # Base confidence for finding similar projects
            reasoning_parts.append(f"Found {len(analysis.similar_projects)} similar projects.")
            # Further increase confidence based on similarity scores or number of projects
            avg_similarity = sum([p.similarity_score for p in analysis.similar_projects]) / len(analysis.similar_projects)
            confidence_score += avg_similarity * 0.2

        if analysis.velocity_trends and analysis.velocity_trends.confidence > self.decision_config.min_velocity_confidence_for_scoring:
            confidence_score += analysis.velocity_trends.confidence * 0.3
            reasoning_parts.append(f"Velocity trend analysis has {analysis.velocity_trends.confidence*100:.0f}% confidence.")

        if analysis.success_indicators and analysis.success_indicators.success_probability > 0.6:
            confidence_score += analysis.success_indicators.success_probability * 0.2
            reasoning_parts.append(f"Success indicators suggest {analysis.success_indicators.success_probability*100:.0f}% probability.")

        final_confidence = min(round(confidence_score, 2), 1.0)
        final_reasoning = ". ".join(reasoning_parts) if reasoning_parts else "Limited historical data for robust pattern analysis."

        logger.debug("Validated pattern confidence", confidence=final_confidence, reasoning=final_reasoning)
        return ConfidenceScore(score=final_confidence, reasoning=final_reasoning)
    
    async def analyze_hybrid_patterns(
        self, 
        project_id: str, 
        project_data: ProjectData,
        episode_context: Optional[EpisodeBasedDecisionContext] = None
    ) -> Tuple[PatternAnalysis, Optional[PatternCombinationResult]]:
        """
        Enhanced pattern analysis that combines Chronicle patterns with episode memory.
        
        Args:
            project_id: Project identifier
            project_data: Current project data
            episode_context: Episode-based decision context from Memory Bridge
            
        Returns:
            Tuple of (enhanced_pattern_analysis, pattern_combination_result)
        """
        logger.info("Starting hybrid pattern analysis with episode memory", project_id=project_id)
        
        with self.performance_monitor.time_operation("hybrid_pattern_analysis"):
            # Check for cached hybrid analysis first
            episode_context_hash = hash(str(episode_context.dict())) if episode_context else 0
            cache_key = f"hybrid_analysis_{project_id}_{episode_context_hash}"
            cached_result = pattern_cache.get(cache_key)
            
            if cached_result:
                logger.info("Returning cached hybrid pattern analysis", project_id=project_id)
                self.performance_monitor.record_cache_hit()
                return cached_result[0], cached_result[1]
            
            self.performance_monitor.record_cache_miss()
            self.performance_monitor.increment_hybrid_analysis()
            # Get Chronicle patterns using existing method
            chronicle_analysis = await self.analyze_project_patterns(project_id, project_data)
            
            # If no episode context, return Chronicle-only analysis
            if not episode_context:
                logger.info("No episode context available, returning Chronicle-only analysis")
                return chronicle_analysis, None
            
            # Combine patterns using Pattern Combiner
            with self.performance_monitor.time_operation("pattern_combination"):
                current_project_context = {
                    "project_id": project_id,
                    "team_size": project_data.team_size,
                    "backlog_tasks": project_data.backlog_tasks,
                    "sprint_duration_weeks": getattr(project_data, 'sprint_duration_weeks', 2)
                }
                
                combination_result = self.pattern_combiner.combine_patterns(
                    episode_context=episode_context,
                    chronicle_analysis=chronicle_analysis,
                    current_project_context=current_project_context
                )
                self.performance_monitor.increment_pattern_combination()
            
            # Enhance Chronicle analysis with combined patterns
            enhanced_analysis = self._enhance_chronicle_analysis_with_episodes(
                chronicle_analysis, combination_result, episode_context
            )
            
            logger.info(f"Hybrid pattern analysis complete: {len(combination_result.combined_patterns)} "
                       f"combined patterns, overall confidence: {combination_result.overall_confidence:.2f}")
            
            # Cache the result for future use
            result_tuple = (enhanced_analysis, combination_result)
            pattern_cache.put(cache_key, result_tuple, ttl_minutes=15)  # Cache for 15 minutes
            
            return enhanced_analysis, combination_result
    
    def _enhance_chronicle_analysis_with_episodes(
        self,
        chronicle_analysis: PatternAnalysis,
        combination_result: PatternCombinationResult,
        episode_context: EpisodeBasedDecisionContext
    ) -> PatternAnalysis:
        """Enhance Chronicle analysis with episode-based insights"""
        
        try:
            # Create enhanced success indicators based on combined patterns
            enhanced_success_indicators = chronicle_analysis.success_indicators
            
            # Get combined recommendations
            combined_recommendations = self.pattern_combiner.get_recommended_values(combination_result)
            
            if enhanced_success_indicators and combined_recommendations:
                # Update success indicators with combined recommendations
                if "recommended_task_count" in combined_recommendations:
                    enhanced_success_indicators.optimal_tasks_per_sprint = combined_recommendations["recommended_task_count"]
                
                if "recommended_sprint_duration_weeks" in combined_recommendations:
                    enhanced_success_indicators.recommended_sprint_duration = combined_recommendations["recommended_sprint_duration_weeks"]
                
                # Enhanced success probability based on combination confidence
                enhanced_success_indicators.success_probability = max(
                    enhanced_success_indicators.success_probability,
                    combination_result.overall_confidence
                )
            
            # Add episode metadata to performance metrics
            enhanced_performance_metrics = chronicle_analysis.performance_metrics.copy()
            enhanced_performance_metrics.update({
                "episode_integration": {
                    "episodes_used": episode_context.episodes_used_for_context,
                    "episode_similarity": episode_context.average_episode_similarity,
                    "episode_confidence": episode_context.overall_recommendation_confidence,
                    "combination_confidence": combination_result.overall_confidence,
                    "pattern_sources": combination_result.pattern_source_influence
                }
            })
            
            # Create enhanced analysis
            enhanced_analysis = PatternAnalysis(
                similar_projects=chronicle_analysis.similar_projects,
                velocity_trends=chronicle_analysis.velocity_trends,
                success_indicators=enhanced_success_indicators,
                performance_metrics=enhanced_performance_metrics
            )
            
            return enhanced_analysis
            
        except Exception as e:
            logger.warning(f"Failed to enhance Chronicle analysis with episodes: {e}")
            return chronicle_analysis
    
    def generate_hybrid_insights_summary(
        self, 
        enhanced_analysis: PatternAnalysis, 
        combination_result: Optional[PatternCombinationResult],
        episode_context: Optional[EpisodeBasedDecisionContext]
    ) -> str:
        """Generate human-readable summary including episode insights"""
        
        # Start with base Chronicle insights
        base_summary = self.generate_insights_summary(enhanced_analysis)
        
        if not combination_result or not episode_context:
            return base_summary
        
        # Add episode-based insights
        episode_insights = []
        
        if episode_context.episodes_used_for_context > 0:
            episode_insights.append(
                f"Episode memory: {episode_context.episodes_used_for_context} similar past decisions "
                f"analyzed with {episode_context.average_episode_similarity:.1%} average similarity."
            )
        
        # Add combined pattern insights
        for pattern in combination_result.combined_patterns:
            if pattern.confidence > 0.5:
                source_info = "hybrid intelligence" if (pattern.episode_source_weight > 0 and 
                                                       pattern.chronicle_source_weight > 0) else "single source"
                episode_insights.append(
                    f"Combined {pattern.pattern_type}: {pattern.pattern_value} "
                    f"({pattern.success_rate:.1%} success rate, {source_info})"
                )
        
        # Add key episode insights
        if episode_context.key_insights:
            top_insights = episode_context.key_insights[:2]  # Limit to top 2 insights
            episode_insights.extend([f"Memory insight: {insight}" for insight in top_insights])
        
        # Combine summaries
        if episode_insights:
            full_summary = base_summary + " " + " ".join(episode_insights)
        else:
            full_summary = base_summary
        
        return full_summary
    
    def validate_hybrid_pattern_confidence(
        self, 
        enhanced_analysis: PatternAnalysis,
        combination_result: Optional[PatternCombinationResult]
    ) -> ConfidenceScore:
        """Validate confidence for hybrid pattern analysis"""
        
        # Start with base Chronicle confidence
        base_confidence = self.validate_pattern_confidence(enhanced_analysis)
        
        if not combination_result:
            return base_confidence
        
        # Enhance confidence based on episode integration
        episode_confidence_boost = 0.0
        reasoning_parts = [base_confidence.reasoning]
        
        if combination_result.overall_confidence > 0.3:
            episode_confidence_boost = combination_result.overall_confidence * 0.2  # Up to 20% boost
            reasoning_parts.append(
                f"Episode memory integration adds {episode_confidence_boost:.1%} confidence boost "
                f"from {len(combination_result.combined_patterns)} hybrid patterns."
            )
        
        # Calculate final hybrid confidence
        final_confidence = min(base_confidence.score + episode_confidence_boost, 1.0)
        final_reasoning = " ".join(reasoning_parts)
        
        return ConfidenceScore(score=final_confidence, reasoning=final_reasoning)
    
    async def analyze_strategy_enhanced_patterns(
        self, 
        project_id: str, 
        project_data: ProjectData,
        episode_context: Optional[EpisodeBasedDecisionContext] = None
    ) -> Tuple[PatternAnalysis, Optional[PatternCombinationResult], Dict[str, Any]]:
        """
        Enhanced pattern analysis that combines Chronicle patterns, episode memory, and strategy intelligence.
        
        Args:
            project_id: Project identifier
            project_data: Current project data
            episode_context: Episode-based decision context from Memory Bridge
            
        Returns:
            Tuple of (enhanced_pattern_analysis, pattern_combination_result, strategy_recommendations)
        """
        logger.info("Starting strategy-enhanced pattern analysis", project_id=project_id)
        
        with self.performance_monitor.time_operation("strategy_enhanced_pattern_analysis"):
            # Get hybrid patterns first
            enhanced_analysis, combination_result = await self.analyze_hybrid_patterns(
                project_id, project_data, episode_context
            )
            
            # Get strategy recommendations if strategy repository is available
            strategy_recommendations = {}
            if self.strategy_repository:
                strategy_recommendations = await self._get_strategy_recommendations(
                    project_id, project_data, enhanced_analysis, episode_context
                )
                
                # Enhance pattern analysis with strategy insights
                enhanced_analysis = self._enhance_analysis_with_strategies(
                    enhanced_analysis, strategy_recommendations
                )
            else:
                logger.debug("Strategy repository not available, skipping strategy enhancement")
            
            logger.info(
                f"Strategy-enhanced pattern analysis complete with "
                f"{len(strategy_recommendations.get('applicable_strategies', []))} applicable strategies"
            )
            
            return enhanced_analysis, combination_result, strategy_recommendations
    
    async def _get_strategy_recommendations(
        self,
        project_id: str,
        project_data: ProjectData,
        pattern_analysis: PatternAnalysis,
        episode_context: Optional[EpisodeBasedDecisionContext] = None
    ) -> Dict[str, Any]:
        """Get strategy recommendations for the current project context"""
        try:
            # Build context for strategy matching
            strategy_context = {
                "project_id": project_id,
                "team_size": project_data.team_size,
                "backlog_tasks": project_data.backlog_tasks,
                "sprint_duration_weeks": getattr(project_data, 'sprint_duration_weeks', 2)
            }
            
            # Add pattern analysis insights to context
            if pattern_analysis.similar_projects:
                strategy_context["similar_projects_count"] = len(pattern_analysis.similar_projects)
                strategy_context["avg_similarity_score"] = sum(
                    p.similarity_score for p in pattern_analysis.similar_projects
                ) / len(pattern_analysis.similar_projects)
            
            if pattern_analysis.velocity_trends:
                strategy_context["velocity_trend"] = pattern_analysis.velocity_trends.trend_direction
                strategy_context["current_velocity"] = pattern_analysis.velocity_trends.current_team_velocity
            
            if pattern_analysis.success_indicators:
                strategy_context["success_probability"] = pattern_analysis.success_indicators.success_probability
                strategy_context["optimal_tasks"] = pattern_analysis.success_indicators.optimal_tasks_per_sprint
            
            # Add episode context if available
            if episode_context:
                strategy_context["episodes_used"] = episode_context.episodes_used_for_context
                strategy_context["episode_similarity"] = episode_context.average_episode_similarity
                strategy_context["episode_confidence"] = episode_context.overall_recommendation_confidence
            
            # Find applicable strategies
            applicable_strategies = await self.strategy_repository.find_applicable_strategies(
                context=strategy_context,
                min_confidence=0.3,
                limit=5
            )
            
            # Build strategy recommendations
            strategy_recommendations = {
                "applicable_strategies": [],
                "strategy_context": strategy_context,
                "recommendation_confidence": 0.0,
                "strategy_insights": []
            }
            
            for strategy in applicable_strategies:
                strategy_info = {
                    "strategy_id": str(strategy.knowledge_id),
                    "description": strategy.description,
                    "confidence": strategy.confidence,
                    "success_rate": strategy.success_rate,
                    "times_applied": strategy.times_applied,
                    "strategy_content": strategy.content,
                    "applicability_score": self._calculate_strategy_applicability(strategy, strategy_context)
                }
                
                strategy_recommendations["applicable_strategies"].append(strategy_info)
            
            # Calculate overall recommendation confidence
            if applicable_strategies:
                strategy_recommendations["recommendation_confidence"] = sum(
                    s["applicability_score"] * s["confidence"] 
                    for s in strategy_recommendations["applicable_strategies"]
                ) / len(strategy_recommendations["applicable_strategies"])
                
                # Generate strategy insights
                strategy_recommendations["strategy_insights"] = self._generate_strategy_insights(
                    applicable_strategies, strategy_context
                )
            
            return strategy_recommendations
            
        except Exception as e:
            logger.error(f"Failed to get strategy recommendations: {e}")
            return {"error": str(e)}
    
    def _calculate_strategy_applicability(
        self, 
        strategy, 
        context: Dict[str, Any]
    ) -> float:
        """Calculate how applicable a strategy is to the current context"""
        try:
            # Simple applicability calculation based on strategy content
            applicability_score = 0.5  # Base score
            
            strategy_content = strategy.content
            if not isinstance(strategy_content, dict):
                return applicability_score
            
            # Check context match
            applicability_conditions = strategy_content.get('applicability_conditions', {})
            
            for condition_key, condition_value in applicability_conditions.items():
                if condition_key in context:
                    context_value = context[condition_key]
                    
                    if isinstance(condition_value, dict) and 'min' in condition_value and 'max' in condition_value:
                        # Numeric range condition
                        if condition_value['min'] <= context_value <= condition_value['max']:
                            applicability_score += 0.1
                    elif isinstance(condition_value, list):
                        # Categorical condition
                        if context_value in condition_value:
                            applicability_score += 0.1
                    elif condition_value == context_value:
                        # Exact match condition
                        applicability_score += 0.1
            
            # Factor in strategy performance
            if strategy.success_rate and strategy.success_rate > 0.7:
                applicability_score += 0.1
            
            if strategy.times_applied > 5:
                applicability_score += 0.1
            
            return min(applicability_score, 1.0)
            
        except Exception as e:
            logger.warning(f"Failed to calculate strategy applicability: {e}")
            return 0.5
    
    def _generate_strategy_insights(
        self, 
        strategies: List, 
        context: Dict[str, Any]
    ) -> List[str]:
        """Generate human-readable strategy insights"""
        insights = []
        
        try:
            if not strategies:
                return ["No applicable strategies found for current context"]
            
            # High-confidence strategies
            high_conf_strategies = [s for s in strategies if s.confidence > 0.8]
            if high_conf_strategies:
                insights.append(
                    f"{len(high_conf_strategies)} high-confidence strategies available "
                    f"with average {sum(s.confidence for s in high_conf_strategies) / len(high_conf_strategies):.1%} confidence"
                )
            
            # Success rate insights
            avg_success_rate = sum(s.success_rate or 0 for s in strategies) / len(strategies)
            if avg_success_rate > 0.7:
                insights.append(f"Applicable strategies show {avg_success_rate:.1%} average success rate")
            
            # Experience insights
            total_applications = sum(s.times_applied for s in strategies)
            if total_applications > 20:
                insights.append(f"Strategies have been successfully applied {total_applications} times")
            
            # Context-specific insights
            if context.get('team_size', 0) <= 3:
                small_team_strategies = [
                    s for s in strategies 
                    if 'small_team' in str(s.content).lower()
                ]
                if small_team_strategies:
                    insights.append(f"{len(small_team_strategies)} strategies optimized for small teams")
            
            return insights
            
        except Exception as e:
            logger.warning(f"Failed to generate strategy insights: {e}")
            return ["Strategy analysis completed"]
    
    def _enhance_analysis_with_strategies(
        self,
        pattern_analysis: PatternAnalysis,
        strategy_recommendations: Dict[str, Any]
    ) -> PatternAnalysis:
        """Enhance pattern analysis with strategy recommendations"""
        try:
            # Add strategy metrics to performance metrics
            enhanced_performance_metrics = pattern_analysis.performance_metrics.copy()
            enhanced_performance_metrics.update({
                "strategy_integration": {
                    "applicable_strategies_count": len(strategy_recommendations.get('applicable_strategies', [])),
                    "strategy_recommendation_confidence": strategy_recommendations.get('recommendation_confidence', 0),
                    "strategy_insights": strategy_recommendations.get('strategy_insights', [])
                }
            })
            
            # Enhance success indicators with strategy confidence
            enhanced_success_indicators = pattern_analysis.success_indicators
            if enhanced_success_indicators and strategy_recommendations.get('recommendation_confidence', 0) > 0.5:
                # Boost success probability if we have high-confidence strategy recommendations
                strategy_confidence_boost = strategy_recommendations['recommendation_confidence'] * 0.1
                enhanced_success_indicators.success_probability = min(
                    enhanced_success_indicators.success_probability + strategy_confidence_boost,
                    1.0
                )
            
            # Create enhanced analysis
            enhanced_analysis = PatternAnalysis(
                similar_projects=pattern_analysis.similar_projects,
                velocity_trends=pattern_analysis.velocity_trends,
                success_indicators=enhanced_success_indicators,
                performance_metrics=enhanced_performance_metrics
            )
            
            return enhanced_analysis
            
        except Exception as e:
            logger.warning(f"Failed to enhance analysis with strategies: {e}")
            return pattern_analysis
    
    def generate_strategy_enhanced_insights_summary(
        self,
        enhanced_analysis: PatternAnalysis,
        combination_result: Optional[PatternCombinationResult],
        strategy_recommendations: Dict[str, Any],
        episode_context: Optional[EpisodeBasedDecisionContext] = None
    ) -> str:
        """Generate comprehensive insights summary including strategy recommendations"""
        
        # Start with hybrid insights
        base_summary = self.generate_hybrid_insights_summary(
            enhanced_analysis, combination_result, episode_context
        )
        
        # Add strategy insights
        strategy_insights = []
        
        applicable_strategies = strategy_recommendations.get('applicable_strategies', [])
        if applicable_strategies:
            strategy_insights.append(
                f"Strategy recommendations: {len(applicable_strategies)} applicable strategies identified "
                f"with {strategy_recommendations.get('recommendation_confidence', 0):.1%} overall confidence."
            )
            
            # Add top strategy insights
            top_insights = strategy_recommendations.get('strategy_insights', [])[:2]
            strategy_insights.extend(top_insights)
        
        # Combine all insights
        if strategy_insights:
            full_summary = base_summary + " " + " ".join(strategy_insights)
        else:
            full_summary = base_summary
        
        return full_summary
