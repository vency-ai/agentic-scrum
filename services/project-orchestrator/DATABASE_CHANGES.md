# Database Changes - Strategy Evolution Layer

## Overview
This document tracks all database schema changes required for the Strategy Evolution Layer implementation as per CR_Agent_06_Strategy_Evolution.md.

## Database: agent_memory

### New Tables

#### 1. strategy_performance_log
**Purpose**: Tracks individual strategy applications and outcomes for continuous learning optimization.

```sql
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
```

**Columns:**
- `log_id`: Primary key, auto-generated UUID
- `strategy_id`: Foreign key to agent_knowledge table (CASCADE delete)
- `episode_id`: Foreign key to agent_episodes table (CASCADE delete)  
- `project_id`: Project identifier for filtering
- `application_timestamp`: When the strategy was applied
- `predicted_outcome`: JSONB storing what the strategy predicted
- `actual_outcome`: JSONB storing what actually happened
- `outcome_quality`: Quality score of actual outcome (0.0-1.0)
- `strategy_confidence`: Confidence level when applied (0.0-1.0)
- `context_similarity`: Context similarity to training data (0.0-1.0)
- `performance_delta`: Difference between predicted vs actual performance
- `created_at`, `updated_at`: Standard timestamp fields

### New Indexes

#### strategy_performance_log Indexes
```sql
-- Performance indexes for strategy_performance_log
CREATE INDEX IF NOT EXISTS idx_strategy_performance_log_strategy_id ON strategy_performance_log(strategy_id);
CREATE INDEX IF NOT EXISTS idx_strategy_performance_log_episode_id ON strategy_performance_log(episode_id);
CREATE INDEX IF NOT EXISTS idx_strategy_performance_log_project_id ON strategy_performance_log(project_id);
CREATE INDEX IF NOT EXISTS idx_strategy_performance_log_timestamp ON strategy_performance_log(application_timestamp);
CREATE INDEX IF NOT EXISTS idx_strategy_performance_log_quality ON strategy_performance_log(outcome_quality);
```

#### Enhanced agent_knowledge Indexes
```sql
-- Optimized index for strategy queries
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_strategy_queries ON agent_knowledge(knowledge_type, is_active, confidence DESC, success_rate DESC) 
WHERE knowledge_type = 'strategy';

-- Composite index for strategy evolution queries  
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_evolution ON agent_knowledge(knowledge_type, is_active, last_applied DESC)
WHERE knowledge_type = 'strategy';

-- Partial index for high-performing strategies
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_high_performers ON agent_knowledge(confidence, success_rate)
WHERE knowledge_type = 'strategy' AND is_active = true AND confidence >= 0.7;
```

### New Triggers

#### Auto-update timestamp trigger
```sql
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
```

### Table Comments
```sql
COMMENT ON TABLE strategy_performance_log IS 'Tracks individual strategy applications and outcomes for continuous learning';
COMMENT ON COLUMN strategy_performance_log.strategy_id IS 'Reference to the applied strategy in agent_knowledge table';
COMMENT ON COLUMN strategy_performance_log.episode_id IS 'Reference to the episode where strategy was applied';
COMMENT ON COLUMN strategy_performance_log.predicted_outcome IS 'What the strategy predicted would happen';
COMMENT ON COLUMN strategy_performance_log.actual_outcome IS 'What actually happened';
COMMENT ON COLUMN strategy_performance_log.outcome_quality IS 'Quality score of the actual outcome (0.0 to 1.0)';
COMMENT ON COLUMN strategy_performance_log.strategy_confidence IS 'Confidence level when strategy was applied';
COMMENT ON COLUMN strategy_performance_log.context_similarity IS 'How similar the context was to strategy training contexts';
COMMENT ON COLUMN strategy_performance_log.performance_delta IS 'Difference between predicted and actual performance';
```

## Existing Table Usage

### agent_knowledge (Enhanced)
The existing `agent_knowledge` table is used to store strategy objects with:
- `knowledge_type = 'strategy'` to distinguish strategies from other knowledge
- Enhanced with new indexes for optimal strategy queries
- No schema changes required to existing table

### agent_episodes (Used)  
The existing `agent_episodes` table is used for:
- Pattern extraction from successful episodes (outcome_quality >= 0.85)
- Foreign key relationship with strategy_performance_log
- No schema changes required

## Migration Status

| Component | Status | Applied Date | Notes |
|-----------|--------|--------------|-------|
| strategy_performance_log table | ✅ Applied | 2024-11-01 | Core strategy tracking table |
| Performance indexes | ✅ Applied | 2024-11-01 | Optimized for strategy queries |
| agent_knowledge indexes | ✅ Applied | 2024-11-01 | Enhanced strategy retrieval |
| Timestamp trigger | ✅ Applied | 2024-11-01 | Auto-update mechanism |
| Table comments | ✅ Applied | 2024-11-01 | Documentation |

## Query Performance Expectations

With the new indexes, these query patterns are optimized:

1. **Find applicable strategies**: `WHERE knowledge_type = 'strategy' AND is_active = true ORDER BY confidence DESC`
2. **Strategy performance analysis**: `WHERE strategy_id = ? AND application_timestamp >= ?`
3. **Project-specific queries**: `WHERE project_id = ?`
4. **High-quality outcome analysis**: `WHERE outcome_quality >= 0.85`
5. **Recent applications**: `WHERE application_timestamp >= NOW() - INTERVAL '30 days'`

## Backup Considerations

- All new tables and indexes are in the existing `agent_memory` database
- Foreign key constraints ensure referential integrity
- CASCADE deletes protect against orphaned records
- Regular backup of `agent_memory` database includes all strategy data

## Rollback Plan

If rollback is needed:
```sql
-- Drop in reverse order
DROP TRIGGER IF EXISTS update_strategy_performance_log_updated_at ON strategy_performance_log;
DROP FUNCTION IF EXISTS update_updated_at_column();
DROP INDEX IF EXISTS idx_agent_knowledge_high_performers;
DROP INDEX IF EXISTS idx_agent_knowledge_evolution; 
DROP INDEX IF EXISTS idx_agent_knowledge_strategy_queries;
DROP INDEX IF EXISTS idx_strategy_performance_log_quality;
DROP INDEX IF EXISTS idx_strategy_performance_log_timestamp;
DROP INDEX IF EXISTS idx_strategy_performance_log_project_id;
DROP INDEX IF EXISTS idx_strategy_performance_log_episode_id;
DROP INDEX IF EXISTS idx_strategy_performance_log_strategy_id;
DROP TABLE IF EXISTS strategy_performance_log;
```