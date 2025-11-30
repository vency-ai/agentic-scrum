-- Migration: Add strategy_performance_log table for Strategy Evolution Layer
-- CR: CR_Agent_06_Strategy_Evolution.md
-- Date: 2024-11-01

-- Create strategy_performance_log table
CREATE TABLE IF NOT EXISTS strategy_performance_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id UUID NOT NULL REFERENCES agent_knowledge(knowledge_id) ON DELETE CASCADE,
    episode_id UUID NOT NULL REFERENCES agent_episodes(episode_id) ON DELETE CASCADE,
    project_id VARCHAR(255) NOT NULL,
    application_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    predicted_outcome JSONB,
    actual_outcome JSONB,
    outcome_quality FLOAT CHECK (outcome_quality >= 0.0 AND outcome_quality <= 1.0),
    strategy_confidence FLOAT NOT NULL CHECK (strategy_confidence >= 0.0 AND strategy_confidence <= 1.0),
    context_similarity FLOAT CHECK (context_similarity >= 0.0 AND context_similarity <= 1.0),
    performance_delta FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_strategy_performance_log_strategy_id ON strategy_performance_log(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_performance_log_episode_id ON strategy_performance_log(episode_id);
CREATE INDEX IF NOT EXISTS idx_strategy_performance_log_project_id ON strategy_performance_log(project_id);
CREATE INDEX IF NOT EXISTS idx_strategy_performance_log_timestamp ON strategy_performance_log(application_timestamp);
CREATE INDEX IF NOT EXISTS idx_strategy_performance_log_quality ON strategy_performance_log(outcome_quality);

-- Add index to agent_knowledge table for strategy queries
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_strategy_queries ON agent_knowledge(knowledge_type, is_active, confidence DESC, success_rate DESC) 
WHERE knowledge_type = 'strategy';

-- Add composite index for strategy evolution queries
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_evolution ON agent_knowledge(knowledge_type, is_active, last_applied DESC)
WHERE knowledge_type = 'strategy';

-- Add partial index for high-performing strategies
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_high_performers ON agent_knowledge(confidence, success_rate)
WHERE knowledge_type = 'strategy' AND is_active = true AND confidence >= 0.7;

-- Update trigger for updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_strategy_performance_log_updated_at 
    BEFORE UPDATE ON strategy_performance_log 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Comments for documentation
COMMENT ON TABLE strategy_performance_log IS 'Tracks individual strategy applications and outcomes for continuous learning';
COMMENT ON COLUMN strategy_performance_log.strategy_id IS 'Reference to the applied strategy in agent_knowledge table';
COMMENT ON COLUMN strategy_performance_log.episode_id IS 'Reference to the episode where strategy was applied';
COMMENT ON COLUMN strategy_performance_log.predicted_outcome IS 'What the strategy predicted would happen';
COMMENT ON COLUMN strategy_performance_log.actual_outcome IS 'What actually happened';
COMMENT ON COLUMN strategy_performance_log.outcome_quality IS 'Quality score of the actual outcome (0.0 to 1.0)';
COMMENT ON COLUMN strategy_performance_log.strategy_confidence IS 'Confidence level when strategy was applied';
COMMENT ON COLUMN strategy_performance_log.context_similarity IS 'How similar the context was to strategy training contexts';
COMMENT ON COLUMN strategy_performance_log.performance_delta IS 'Difference between predicted and actual performance';