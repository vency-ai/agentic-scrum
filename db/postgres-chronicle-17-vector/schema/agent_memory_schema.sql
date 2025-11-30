-- =====================================================
-- Agent Memory Database Schema
-- Version: 1.0.0
-- CR: CR_Agent_01
-- =====================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- =====================================================
-- Table: agent_episodes
-- =====================================================
CREATE TABLE agent_episodes (
    episode_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    perception JSONB NOT NULL,
    reasoning JSONB NOT NULL,
    action JSONB NOT NULL,
    outcome JSONB,
    outcome_quality FLOAT CHECK (outcome_quality BETWEEN 0 AND 1),
    outcome_recorded_at TIMESTAMPTZ,
    
    embedding vector(1536),
    
    agent_version VARCHAR(20) NOT NULL,
    control_mode VARCHAR(50) DEFAULT 'rule_based_only',
    decision_source VARCHAR(50),
    sprint_id VARCHAR(50),
    chronicle_note_id UUID,
    
    CONSTRAINT chk_control_mode CHECK (control_mode IN ('rule_based_only', 'intelligence_enhanced', 'memory_augmented'))
);

CREATE INDEX idx_episodes_project_time ON agent_episodes(project_id, timestamp DESC);
CREATE INDEX idx_episodes_quality ON agent_episodes(outcome_quality DESC) WHERE outcome_quality IS NOT NULL;
CREATE INDEX idx_episodes_decision_source ON agent_episodes(decision_source);
CREATE INDEX idx_episodes_sprint ON agent_episodes(sprint_id) WHERE sprint_id IS NOT NULL;
CREATE INDEX idx_episodes_no_outcome ON agent_episodes(episode_id) WHERE outcome IS NULL;

CREATE INDEX idx_episodes_embedding ON agent_episodes 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- =====================================================
-- Table: agent_knowledge
-- =====================================================
CREATE TABLE agent_knowledge (
    knowledge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_type VARCHAR(50) NOT NULL,
    
    content JSONB NOT NULL,
    description TEXT NOT NULL,
    
    confidence FLOAT DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    supporting_episodes UUID[] NOT NULL DEFAULT '{}',
    contradicting_episodes UUID[] DEFAULT '{}',
    
    times_applied INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    success_rate FLOAT GENERATED ALWAYS AS (
        CASE WHEN (success_count + failure_count) > 0
        THEN success_count::FLOAT / (success_count + failure_count)
        ELSE NULL END
    ) STORED,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_validated TIMESTAMPTZ,
    last_applied TIMESTAMPTZ,
    
    embedding vector(1536),
    
    created_by VARCHAR(50) DEFAULT 'system',
    is_active BOOLEAN DEFAULT true,
    
    CONSTRAINT chk_knowledge_type CHECK (knowledge_type IN ('strategy', 'pattern', 'constraint', 'heuristic')),
    CONSTRAINT chk_min_supporting_episodes CHECK (array_length(supporting_episodes, 1) >= 3)
);

CREATE INDEX idx_knowledge_type_confidence ON agent_knowledge(knowledge_type, confidence DESC) WHERE is_active = true;
CREATE INDEX idx_knowledge_success_rate ON agent_knowledge(success_rate DESC) WHERE is_active = true;
CREATE INDEX idx_knowledge_last_applied ON agent_knowledge(last_applied DESC);

CREATE INDEX idx_knowledge_embedding ON agent_knowledge 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- =====================================================
-- Table: agent_working_memory
-- =====================================================
CREATE TABLE agent_working_memory (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(50) NOT NULL,
    user_id VARCHAR(100),
    
    current_goal TEXT,
    active_context JSONB,
    thought_history JSONB[] DEFAULT '{}',
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '1 hour',
    is_active BOOLEAN DEFAULT true,
    
    related_episodes UUID[] DEFAULT '{}'
);

CREATE INDEX idx_working_memory_project ON agent_working_memory(project_id, last_updated DESC) WHERE is_active = true;
CREATE INDEX idx_working_memory_expiry ON agent_working_memory(expires_at) WHERE is_active = true;
CREATE INDEX idx_working_memory_user ON agent_working_memory(user_id, project_id);

-- =====================================================
-- Table: agent_memory_metrics
-- =====================================================
CREATE TABLE agent_memory_metrics (
    metric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    
    operation_type VARCHAR(50),
    latency_ms INTEGER,
    results_count INTEGER,
    
    recall_accuracy FLOAT,
    precision FLOAT,
    
    memory_usage_mb FLOAT,
    cpu_percent FLOAT,
    
    project_id VARCHAR(50),
    episode_count INTEGER,
    strategy_count INTEGER
);

CREATE INDEX idx_memory_metrics_timestamp ON agent_memory_metrics(timestamp DESC);
CREATE INDEX idx_memory_metrics_operation ON agent_memory_metrics(operation_type, timestamp DESC);

-- =====================================================
-- Functions and Triggers
-- =====================================================

CREATE OR REPLACE FUNCTION cleanup_expired_working_memory()
RETURNS void AS $$
BEGIN
    UPDATE agent_working_memory
    SET is_active = false
    WHERE expires_at < NOW() AND is_active = true;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_working_memory_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.last_updated = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_working_memory_timestamp
    BEFORE UPDATE ON agent_working_memory
    FOR EACH ROW
    EXECUTE FUNCTION update_working_memory_timestamp();

CREATE OR REPLACE FUNCTION record_memory_operation(
    p_operation_type VARCHAR,
    p_latency_ms INTEGER,
    p_results_count INTEGER,
    p_project_id VARCHAR DEFAULT NULL
)
RETURNS void AS $$
BEGIN
    INSERT INTO agent_memory_metrics (
        operation_type, latency_ms, results_count, project_id
    ) VALUES (
        p_operation_type, p_latency_ms, p_results_count, p_project_id
    );
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- Views for Monitoring
-- =====================================================

CREATE VIEW v_episode_quality_by_project AS
SELECT 
    project_id,
    COUNT(*) as total_episodes,
    COUNT(outcome_quality) as episodes_with_outcome,
    AVG(outcome_quality) as avg_quality,
    STDDEV(outcome_quality) as stddev_quality,
    MIN(outcome_quality) as min_quality,
    MAX(outcome_quality) as max_quality,
    decision_source,
    MAX(timestamp) as last_episode
FROM agent_episodes
GROUP BY project_id, decision_source;

CREATE VIEW v_strategy_effectiveness AS
SELECT 
    knowledge_id,
    description,
    confidence,
    times_applied,
    success_rate,
    array_length(supporting_episodes, 1) as supporting_count,
    EXTRACT(EPOCH FROM (NOW() - last_applied)) / 86400 as days_since_applied,
    is_active
FROM agent_knowledge
WHERE knowledge_type = 'strategy'
ORDER BY confidence DESC, success_rate DESC;

CREATE VIEW v_memory_system_health AS
SELECT
    (SELECT COUNT(*) FROM agent_episodes) as total_episodes,
    (SELECT COUNT(*) FROM agent_episodes WHERE outcome IS NOT NULL) as episodes_with_outcome,
    (SELECT COUNT(*) FROM agent_knowledge WHERE is_active = true) as active_strategies,
    (SELECT COUNT(*) FROM agent_working_memory WHERE is_active = true) as active_sessions,
    (SELECT AVG(latency_ms) FROM agent_memory_metrics WHERE operation_type = 'recall_similar' AND timestamp > NOW() - INTERVAL '1 hour') as avg_recall_latency_ms,
    (SELECT pg_size_pretty(pg_database_size('agent_memory'))) as database_size;

-- =====================================================
-- Grant Permissions
-- =====================================================

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO chronicle_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO chronicle_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO chronicle_user;

-- =====================================================
-- Schema Version Tracking
-- =====================================================

CREATE TABLE schema_version (
    version VARCHAR(20) PRIMARY KEY,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    description TEXT
);

INSERT INTO schema_version (version, description) 
VALUES ('1.0.0', 'Initial agent memory schema - CR_Agent_01');