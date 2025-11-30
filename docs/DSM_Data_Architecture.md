# DSM Data Architecture

## Overview

This document provides a comprehensive overview of the data architecture for the DSM (Digital Scrum Master) microservices. It includes detailed data models, database schemas, and entity-relationship diagrams (ERDs) for each core service.

---

## 1. Project Service Data Architecture

### 1.0 Service Summary
*   **Responsibilities:** Manages core project information, team members, their roles and designations, and tracks team availability through PTO and holiday calendars.
*   **Dependencies:** PostgreSQL (`project-db`).
*   **APIs:** Exposes APIs for creating, retrieving, updating, and deleting projects, managing team members, and querying calendar information.
*   **Resilience Patterns:** N/A (not explicitly defined in data architecture)



### 1.1 Data Models

#### Project Model (Pydantic)
```python
class Project(BaseModel):
    prjid: str          # Unique identifier (e.g., "APO009")
    projectname: str        # Project name (e.g., "Project Apollo")
    codename: str # Brief description
    status: str      # Project status (e.g., "active", "inactive")

    class Config:
        schema_extra = {
            "example": {
                "prjid": "APO009",
                "projectname": "Project Apollo",
                "codename": "Moon landing simulation project",
                "status": "active"
            }
        }
```

#### Team Management Models (Pydantic)
```python
class TeamMember(BaseModel):
    id: str
    name: str | None = None

class EmployeeCreate(BaseModel):
    id: str
    name: str
    gender: Optional[str] = None
    state: Optional[str] = None
    age: Optional[int] = None
    project_assign: Optional[bool] = None
    active: Optional[bool] = None

class TeamMembersAssign(BaseModel):
    employee_ids: List[str]

class ProjectStatus(BaseModel):
    status: str
```

#### Calendar Models (Pydantic)
```python
class PTORequest(BaseModel):
    start_date: datetime
    end_date: datetime
    reason: str | None = None

class PTOResponse(PTORequest):
    pto_id: uuid.UUID
    employee_id: str
    created_at: datetime

class Holiday(BaseModel):
    holiday_date: date
    holiday_name: str
    type: str | None = None

class AvailabilityConflict(BaseModel):
    type: str  # 'holiday' or 'pto'
    date: date
    name: str  # Holiday name or employee name
    details: str  # Additional details

class AvailabilityResponse(BaseModel):
    status: str  # 'ok' or 'conflict'
    conflicts: List[AvailabilityConflict] = []
```

### 1.2 Database Schema
```sql
-- Projects table
CREATE TABLE projects (
    prjid VARCHAR(255) PRIMARY KEY,
    projectname VARCHAR(255) NOT NULL,
    codename VARCHAR(255) NOT NULL,
    status VARCHAR(255) DEFAULT 'inactive'
);

-- Teams table
CREATE TABLE teams (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    gender VARCHAR(10),
    state VARCHAR(50),
    age INTEGER,
    project_assign BOOLEAN,
    active BOOLEAN
);

-- Designations table
CREATE TABLE designations (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    experience VARCHAR(50),
    years INTEGER
);

-- Roles table
CREATE TABLE roles (
    id VARCHAR(255) PRIMARY KEY,
    role VARCHAR(255) NOT NULL
);

-- Project team mappings
CREATE TABLE project_team_mapping (
    project_id VARCHAR(255) NOT NULL,
    employee_id VARCHAR(255) NOT NULL,
    PRIMARY KEY (project_id, employee_id)
);

-- Team designation mappings
CREATE TABLE team_designation_mapping (
    id VARCHAR(255) PRIMARY KEY,
    did VARCHAR(255) NOT NULL,
    eid VARCHAR(255) NOT NULL
);

-- Team role mappings
CREATE TABLE team_role_mapping (
    id VARCHAR(255) PRIMARY KEY,
    rid VARCHAR(255) NOT NULL,
    eid VARCHAR(255) NOT NULL
);

-- Role designation mappings
CREATE TABLE role_designation_mapping (
    id VARCHAR(255) PRIMARY KEY,
    roleid VARCHAR(255) NOT NULL,
    did VARCHAR(255) NOT NULL
);

-- PTO calendar
CREATE TABLE pto_calendar (
    pto_id VARCHAR(255) PRIMARY KEY,
    employee_id VARCHAR(255) NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- US holidays
CREATE TABLE us_holidays (
    holiday_date DATE PRIMARY KEY,
    holiday_name VARCHAR(255) NOT NULL,
    type VARCHAR(50)
);
```

### 1.3 Entity Relationship Diagram (ERD)
```mermaid
erDiagram
    projects {
        VARCHAR(255) prjid PK
        VARCHAR(255) projectname
        VARCHAR(255) codename
        VARCHAR(255) status
    }

    teams {
        VARCHAR(255) id PK
        VARCHAR(255) name
        VARCHAR(10) gender
        VARCHAR(50) state
        INTEGER age
        BOOLEAN project_assign
        BOOLEAN active
    }

    designations {
        VARCHAR(255) id PK
        VARCHAR(255) name
        VARCHAR(50) experience
        INTEGER years
    }

    roles {
        VARCHAR(255) id PK
        VARCHAR(255) role
    }

    project_team_mapping {
        VARCHAR(255) project_id PK, FK
        VARCHAR(255) employee_id PK, FK
    }

    team_designation_mapping {
        VARCHAR(255) id PK
        VARCHAR(255) did FK
        VARCHAR(255) eid FK
    }

    team_role_mapping {
        VARCHAR(255) id PK
        VARCHAR(255) rid FK
        VARCHAR(255) eid FK
    }

    role_designation_mapping {
        VARCHAR(255) id PK
        VARCHAR(255) roleid FK
        VARCHAR(255) did FK
    }

    pto_calendar {
        VARCHAR(255) pto_id PK
        VARCHAR(255) employee_id FK
        TIMESTAMP start_date
        TIMESTAMP end_date
        TEXT reason
        TIMESTAMP created_at
    }

    us_holidays {
        DATE holiday_date PK
        VARCHAR(255) holiday_name
        VARCHAR(50) type
    }

    projects ||--o{ project_team_mapping : "has"
    teams ||--o{ project_team_mapping : "assigned to"
    teams ||--o{ team_designation_mapping : "has"
    designations ||--o{ team_designation_mapping : "assigned to"
    teams ||--o{ team_role_mapping : "has"
    roles ||--o{ team_role_mapping : "assigned to"
    roles ||--o{ role_designation_mapping : "has"
    designations ||--o{ role_designation_mapping : "assigned to"
    teams ||--o{ pto_calendar : "requests"
```

---

## 2. Backlog Service Data Architecture

### 2.0 Service Summary
*   **Responsibilities:** Manages individual tasks, user stories, and their relationships within the project backlog. Tracks task status and assignment.
*   **Dependencies:** PostgreSQL (`backlog-db`), consumes `task_update_events` from Redis Streams.
*   **APIs:** Provides APIs for creating, retrieving, updating, and deleting tasks and stories.
*   **Resilience Patterns:** N/A (not explicitly defined in data architecture)



### 2.1 Data Models

#### Task Model (Pydantic)
```python
class Task(BaseModel):
    task_id: str
    project_id: str
    title: str
    description: str
    status: str = "unassigned"
    assigned_to: Optional[str] = None
    sprint_id: Optional[str] = None
    progress_percentage: Optional[int] = 0

    class Config:
        schema_extra = {
            "example": {
                "task_id": "TEST001-TASK001",
                "project_id": "TEST001",
                "title": "Setup development environment",
                "description": "Configure IDEs and necessary tools",
                "status": "unassigned",
                "assigned_to": None,
                "sprint_id": None,
                "progress_percentage": 0
            }
        }
```

#### TaskUpdate Model (Pydantic)
```python
class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    sprint_id: Optional[str] = None
    progress_percentage: Optional[int] = None
```

### 2.2 Database Schema
```sql
-- Tasks table
CREATE TABLE tasks (
    task_id VARCHAR(255) PRIMARY KEY,
    project_id VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50),
    assigned_to VARCHAR(255),
    sprint_id VARCHAR(255),
    progress_percentage INTEGER
);

-- Stories table
CREATE TABLE stories (
    id VARCHAR(255) PRIMARY KEY,
    description TEXT NOT NULL
);

-- Story-task relationships
CREATE TABLE story_tasks (
    story_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    PRIMARY KEY (story_id, task_id)
);
```

### 2.3 Entity Relationship Diagram (ERD)
```mermaid
erDiagram
    tasks {
        VARCHAR(255) task_id PK
        VARCHAR(255) project_id
        VARCHAR(255) title
        TEXT description
        VARCHAR(50) status
        VARCHAR(255) assigned_to
        VARCHAR(255) sprint_id
        INTEGER progress_percentage
    }

    stories {
        VARCHAR(255) id PK
        TEXT description
    }

    story_tasks {
        VARCHAR(255) story_id PK
        VARCHAR(255) task_id PK
    }

    stories |o..o| story_tasks : "logically contains"
    tasks |o..o| story_tasks : "logically part of"
```

---

## 3. Sprint Service Data Architecture

### 3.0 Service Summary
*   **Responsibilities:** Manages sprint lifecycle, assigns tasks to sprints, tracks task progress within active sprints, and publishes task progress events.
*   **Dependencies:** PostgreSQL (`sprint-db`), Redis Streams (publishes `daily_scrum_events`, consumes `task_update_events`).
*   **APIs:** Offers APIs for sprint creation, management, and task progress updates.
*   **Resilience Patterns:** N/A (not explicitly defined in data architecture)
*   **Tables Owned:**
    - `sprints` - Sprint information
    - `tasks` - Local copy of tasks for sprint management (progress tracking)
    - `stories` - User stories associated with the sprint
    - `story_tasks` - Link between stories and tasks



### 3.1 Data Models

#### Sprint Model (Pydantic)
```python
class Sprint(BaseModel):
    sprint_id: str
    project_id: str
    sprint_name: str
    start_date: datetime
    end_date: datetime
    duration_weeks: int
    status: str

    class Config:
        schema_extra = {
            "example": {
                "sprint_id": "TEST001-S01",
                "project_id": "TEST001",
                "start_date": "2025-07-28",
                "end_date": "2025-08-11",
                "status": "active"
            }
        }

class SprintTaskSummary(BaseModel):
    total_tasks: int
    completed_tasks: int
    pending_tasks: int
```

#### SprintTaskUpdate Model (Pydantic)
```python
class SprintTaskUpdate(BaseModel):
    status: Optional[str] = None
    progress_percentage: Optional[int] = None

    @validator('progress_percentage')
    def validate_progress(cls, v):
        if v is not None and (v < 0 or v > 100):
            raise ValueError('Progress percentage must be between 0 and 100')
        return v
```

### 3.2 Database Schema
```sql
-- Sprints table
CREATE TABLE sprints (
    sprint_id VARCHAR(50) PRIMARY KEY,
    project_id VARCHAR(50) NOT NULL,
    sprint_name VARCHAR(255),
    start_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    end_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    duration_weeks INTEGER,
    status VARCHAR(50) NOT NULL
);

-- Sprint tasks (local copy for sprint management)
CREATE TABLE tasks (
    task_id VARCHAR(50) PRIMARY KEY,
    sprint_id VARCHAR(20) NOT NULL REFERENCES sprints(sprint_id),
    title VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,
    progress_percentage INTEGER DEFAULT 0,
    assigned_to VARCHAR(255)
);

-- Stories table
CREATE TABLE stories (
    id VARCHAR(255) PRIMARY KEY,
    description TEXT NOT NULL
);

-- Story-task relationships
CREATE TABLE story_tasks (
    story_id VARCHAR(255) NOT NULL,
    task_id VARCHAR(255) NOT NULL,
    PRIMARY KEY (story_id, task_id)
);
```

### 3.3 Entity Relationship Diagram (ERD)
```mermaid
erDiagram
    sprints {
        VARCHAR(50) sprint_id PK
        VARCHAR(50) project_id
        VARCHAR(255) sprint_name
        TIMESTAMP start_date
        TIMESTAMP end_date
        INTEGER duration_weeks
        VARCHAR(50) status
    }

    tasks {
        VARCHAR(50) task_id PK
        VARCHAR(20) sprint_id FK
        VARCHAR(255) title
        VARCHAR(50) status
        INTEGER progress_percentage
        VARCHAR(255) assigned_to
    }

    stories {
        VARCHAR(255) id PK
        TEXT description
    }

    story_tasks {
        VARCHAR(255) story_id PK
        VARCHAR(255) task_id PK
    }

    sprints ||--o{ tasks : "contains"
    stories |o..o| story_tasks : "has"
    tasks |o..o| story_tasks : "is part of"
```

---

## 4. Chronicle Service Data Architecture

### 4.0 Service Summary
*   **Responsibilities:** Serves as the historical record for daily scrum reports and sprint retrospectives. It also hosts the AI Agent's memory system, which includes episodic, semantic, and working memory for advanced decision-making.
*   **Dependencies:** PostgreSQL (`chronicle-db`), receives daily scrum reports from the Sprint Service or an orchestrator.
*   **APIs:** Provides APIs for storing and retrieving historical daily scrum reports, sprint retrospectives, and agent memory data.
*   **Resilience Patterns:** N/A (not explicitly defined in data architecture)
*   **Infrastructure Note:** The underlying `chronicle-db` PostgreSQL instance has been upgraded to **PostgreSQL 17** and includes the **`pgvector` extension**. All connections are managed through **PgBouncer** for efficient connection pooling. This instance supports two logical databases:
    *   `chronicle_db`: For historical scrum and sprint data.
    *   `agent_memory`: A new database dedicated to storing agent memories (episodes, knowledge) with vector embeddings for similarity search.

### 4.1 Data Models

```python
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import datetime
import uuid

class TaskReport(BaseModel):
    id: str
    yesterday_work: Optional[str] = None
    today_work: Optional[str] = None
    impediments: Optional[str] = None
    created_at: datetime.datetime

class EmployeeReport(BaseModel):
    employee_id: Optional[str] = Field(None, alias='assigned_to')
    tasks: List[TaskReport]

    class Config:
        populate_by_name = True

class SummaryMetrics(BaseModel):
    total_team_members: int
    total_tasks: int
    completed_tasks: int
    pending_tasks: int

class DailyScrumReportNote(BaseModel):
    project_id: str
    sprint_id: Optional[str] = None
    report_date: Optional[datetime.date] = None
    summary: Optional[str] = None
    summary_metrics: Optional[SummaryMetrics] = None
    reports: Dict[str, List[EmployeeReport]]

class SprintPlanningNote(BaseModel):
    project_id: str
    sprint_id: str
    sprint_goal: str
    planned_tasks: List[str]

class ActionItem(BaseModel):
    description: str
    status: str = "open"

class TaskSummaryItem(BaseModel):
    description: str
    status: str
    task_id: str
    employee_id: str
    progress_percentage: int

class SprintRetrospectiveNote(BaseModel):
    sprint_id: str
    project_id: str
    sprint_name: Optional[str] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    duration_weeks: Optional[int] = None
    what_went_well: Optional[str] = None
    what_could_be_improved: Optional[str] = None
    action_items: List[ActionItem] = []
    facilitator_id: Optional[str] = None
    attendees: List[str] = []
    tasks_summary: List[TaskSummaryItem] = []

class EmployeeReportResponse(BaseModel):
    employee_id: Optional[str]
    tasks: List[TaskReport]

class DailyScrumReportResponse(BaseModel):
    project_id: str
    sprint_id: str
    created_at: datetime.datetime
    summary: str
    summary_metrics: Optional[SummaryMetrics] = None
    reports: Dict[str, List[EmployeeReportResponse]]

class Episode(BaseModel):
    """Represents an orchestration episode"""
    id: Optional[uuid.UUID] = None
    episode_type: str = "orchestration_decision"
    project_id: str

    context: Dict[str, any]
    decision: Dict[str, any]
    actions: List[str]
    patterns: Dict[str, any]

    outcome: Optional[Dict[str, any]] = None
    outcome_quality: Optional[float] = None

    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    requires_embedding: bool = False

    class Config:
        json_encoders = {
            datetime.datetime: lambda v: v.isoformat(),
            uuid.UUID: lambda v: str(v)
        }

class Strategy(BaseModel):
    """Represents a learned strategy"""
    knowledge_id: Optional[uuid.UUID] = None
    knowledge_type: str = "strategy"

    content: Dict[str, any]
    description: str

    confidence: float = 0.5
    supporting_episodes: List[uuid.UUID] = Field(default_factory=list)
    contradicting_episodes: List[uuid.UUID] = Field(default_factory=list)

    times_applied: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: Optional[float] = None

    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    last_validated: Optional[datetime.datetime] = None
    last_applied: Optional[datetime.datetime] = None

    created_by: str = "system"
    is_active: bool = True

class WorkingMemorySession(BaseModel):
    """Pydantic model for active session context"""
    session_id: uuid.UUID
    project_id: str
    user_id: Optional[str] = None
    current_goal: Optional[str] = None
    active_context: Optional[Dict[str, any]] = None
    thought_history: List[Dict[str, any]] = Field(default_factory=list)
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    last_updated: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    expires_at: datetime.datetime
    is_active: bool = True
    related_episodes: List[uuid.UUID] = Field(default_factory=list)

```

### 4.2 Database Schema
```sql
-- chronicle_notes table
-- This table acts as a general ledger for events and notes.
-- For 'daily_scrum_report' event_type, the detailed report is stored in 'additional_data' (JSONB),
-- and 'summary_metrics' (JSONB) holds aggregated data. The columns 'employee_id',
-- 'yesterday_work', 'today_work', and 'impediments' are legacy fields and are no longer populated
-- for new daily scrum reports but are kept for historical data compatibility.
CREATE TABLE chronicle_notes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(255) NOT NULL,
    project_id VARCHAR(255),
    sprint_id VARCHAR(255),
    note_content TEXT,
    report_date DATE,
    employee_id VARCHAR(255),
    yesterday_work TEXT,
    today_work TEXT,
    impediments TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    summary_metrics JSONB,
    additional_data JSONB,
    summary TEXT
);

-- sprint_retrospectives table
CREATE TABLE sprint_retrospectives (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    sprint_id VARCHAR(255) NOT NULL UNIQUE,
    project_id VARCHAR(255) NOT NULL,
    what_went_well TEXT,
    what_could_be_improved TEXT,
    facilitator_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    sprint_name TEXT,
    start_date DATE,
    end_date DATE,
    duration_weeks INTEGER,
    tasks_summary JSONB
);

-- retrospective_action_items table
CREATE TABLE retrospective_action_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    retrospective_id uuid NOT NULL REFERENCES sprint_retrospectives(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'open'
);

-- retrospective_attendees table
CREATE TABLE retrospective_attendees (
    retrospective_id uuid NOT NULL REFERENCES sprint_retrospectives(id) ON DELETE CASCADE,
    employee_id VARCHAR(255) NOT NULL,
    PRIMARY KEY (retrospective_id, employee_id)
);

-- Agent Memory Schema (within the same PostgreSQL instance)
-- New logical database: agent_memory

-- agent_episodes table
CREATE TABLE agent_episodes (
    episode_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id VARCHAR(50) NOT NULL,
    episode_type VARCHAR(255) NOT NULL,  -- e.g., "orchestration_decision"
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    context JSONB NOT NULL,              -- Complete project context and state
    decision JSONB NOT NULL,             -- Decision details and reasoning
    actions JSONB NOT NULL,              -- Actions taken
    patterns JSONB,                      -- Pattern analysis results
    outcome JSONB,                       -- What happened (null until known)
    outcome_quality FLOAT CHECK (outcome_quality BETWEEN 0 AND 1),
    outcome_recorded_at TIMESTAMPTZ,
    embedding vector(1024),              -- Vector for similarity search
    requires_embedding BOOLEAN DEFAULT false, -- Flag for backfill process
    agent_version VARCHAR(20) NOT NULL,
    control_mode VARCHAR(50) DEFAULT 'rule_based_only',
    decision_source VARCHAR(50),
    sprint_id VARCHAR(50),
    chronicle_note_id UUID
);

-- agent_knowledge table
CREATE TABLE agent_knowledge (
    knowledge_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    knowledge_type VARCHAR(50) NOT NULL, -- 'strategy', 'pattern', 'constraint', 'heuristic'
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
    embedding vector(1024),
    created_by VARCHAR(50) DEFAULT 'system',
    is_active BOOLEAN DEFAULT true
);

-- agent_working_memory table
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

-- agent_memory_metrics table
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

-- strategy_performance_log table
CREATE TABLE strategy_performance_log (
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

### 4.3 Entity Relationship Diagram (ERD)
```mermaid
erDiagram
    sprint_retrospectives {
        uuid id PK
        VARCHAR(255) sprint_id
        VARCHAR(255) project_id
        TEXT what_went_well
        TEXT what_could_be_improved
        VARCHAR(255) facilitator_id
        TIMESTAMP created_at
        TEXT sprint_name
        DATE start_date
        DATE end_date
        INTEGER duration_weeks
        JSONB tasks_summary
    }

    retrospective_action_items {
        uuid id PK
        uuid retrospective_id FK
        TEXT description
        VARCHAR(50) status
    }

    retrospective_attendees {
        uuid retrospective_id FK
        VARCHAR(255) employee_id
    }

    chronicle_notes {
        uuid id PK
        VARCHAR(255) event_type
        VARCHAR(255) project_id
        VARCHAR(255) sprint_id
        TEXT note_content
        DATE report_date
        VARCHAR(255) employee_id
        TEXT yesterday_work
        TEXT today_work
        TEXT impediments
        TIMESTAMP created_at
        JSONB summary_metrics
        JSONB additional_data
        TEXT summary
    }

    sprint_retrospectives ||--o{ retrospective_action_items : "has"
    sprint_retrospectives ||--o{ retrospective_attendees : "has"

    agent_episodes {
        UUID episode_id PK
        VARCHAR(50) project_id
        VARCHAR(255) episode_type
        TIMESTAMPTZ timestamp
        JSONB context
        JSONB decision
        JSONB actions
        JSONB patterns
        JSONB outcome
        FLOAT outcome_quality
        TIMESTAMPTZ outcome_recorded_at
        vector(1024) embedding
        BOOLEAN requires_embedding
        VARCHAR(20) agent_version
        VARCHAR(50) control_mode
        VARCHAR(50) decision_source
    }

    agent_knowledge {
        UUID knowledge_id PK
        VARCHAR(50) knowledge_type
        JSONB content
        TEXT description
        FLOAT confidence
        UUID[] supporting_episodes
        UUID[] contradicting_episodes
        FLOAT success_rate
        TIMESTAMPTZ last_applied
        vector(1024) embedding
        BOOLEAN is_active
    }

    strategy_performance_log {
        UUID log_id PK
        UUID strategy_id FK
        UUID episode_id FK
        VARCHAR(255) project_id
        TIMESTAMP application_timestamp
        FLOAT outcome_quality
    }

    agent_working_memory {
        UUID session_id PK
        VARCHAR(50) project_id
        TEXT current_goal
        JSONB active_context
        TIMESTAMPTZ expires_at
        BOOLEAN is_active
        UUID[] related_episodes
    }

    agent_memory_metrics {
        UUID metric_id PK
        TIMESTAMPTZ timestamp
        VARCHAR(50) operation_type
        INTEGER latency_ms
        INTEGER results_count
        FLOAT recall_accuracy
        FLOAT precision
    }

    agent_knowledge ||--o{ strategy_performance_log : "is tracked by"
    agent_episodes ||--o{ strategy_performance_log : "informs"
```

---

## 5. Project Orchestration Service Data Architecture

### 5.0 Service Summary
*   **Responsibilities:** Provides rule-based and data-driven autonomous project management, transforming it from a pattern-recognition system into a true learning agent. It analyzes the current state of projects, sprints, and backlogs, and leverages its **Strategy Evolution Layer** to make decisions. This layer allows the service to extract reusable strategies from successful historical decisions, store them in a **Strategy Repository** (`agent_knowledge`), and continuously optimize them based on performance outcomes. For decision-making, it prioritizes these learned strategies before falling back to historical episode analysis and Chronicle analytics.
*   **Dependencies:** Project Service, Backlog Service, Sprint Service, Chronicle Service, the `agent_memory` database, and the internal **Ollama LLM Service**.
*   **APIs:** Exposes endpoints to trigger project analysis and orchestration. The response for an orchestration decision is enriched with an optional `ai_agent_advisory` object and a `strategy_context` object that details the influence of learned strategies.
*   **Database:** The service is **stateless** regarding business data but is critically dependent on the `agent_memory` database for its intelligence and learning capabilities. It reads from `agent_episodes` and `agent_knowledge`, and writes to `strategy_performance_log` to create a continuous learning loop.

### 5.1 Data Models

#### Orchestration API Response Models (Pydantic)

```python
class IntelligenceAdjustments(BaseModel):
    """Details on how a learned strategy modified the decision."""
    task_count_modification: Dict[str, any]

class StrategyContext(BaseModel):
    """Provides transparency into which strategies were considered and applied."""
    strategies_evaluated: int
    strategies_applied: int
    best_match_strategy: Dict[str, any]
    fallback_to_episodes: bool
    strategy_influence_weight: float

class OrchestrationDecision(BaseModel):
    """The core decision object, now including the source of intelligence."""
    create_new_sprint: bool
    tasks_to_assign: int
    decision_source: str  # e.g., "rule_based", "intelligence_enhanced", "strategy_enhanced"
    reasoning: str

class AIAgentAdvisory(BaseModel):
    """Represents the AI-generated review of an orchestration decision."""
    enabled: bool
    model: str
    summary: str
    recommendations: List[str]
    risk_assessment: str
    generation_time_ms: float
    error: Optional[str] = None
    fallback: Optional[str] = None

class OrchestrationResponse(BaseModel):
    """The full API response for an orchestration request."""
    project_id: str
    decisions: OrchestrationDecision
    intelligence_adjustments: Optional[IntelligenceAdjustments] = None
    strategy_context: Optional[StrategyContext] = None
    ai_agent_advisory: Optional[AIAgentAdvisory] = None
```

### 5.2 Data Interactions

The Project Orchestrator is a central hub for data aggregation and decision-making. With the Strategy Evolution Layer, its data interaction pattern prioritizes learned knowledge.

*   **Reads (Decision-Making Priority Order):**
    1.  **Agent Memory DB (`agent_knowledge` table):** First, it queries the **Strategy Repository** for high-confidence strategies that match the current project context. This is the primary and fastest source of intelligence.
    2.  **Chronicle Service (Analytics):** If no high-confidence strategy is found, it reads long-term historical project data from the analytics endpoints as a secondary intelligence source.
    3.  **Agent Memory DB (`agent_episodes` table):** As a tertiary source, it performs a vector similarity search to retrieve the top 5 most similar past episodes for fine-grained pattern analysis.
    4.  **Core Services (Project, Backlog, Sprint):** Reads the current state of the project, backlog, and sprints to build the decision context.
    5.  **Ollama LLM Service:** After a decision is finalized, it sends the decision context to the local Ollama server to generate a natural language summary. This is a non-blocking call.

*   **Writes:**
    *   **Agent Memory DB (`strategy_performance_log` table):** When a learned strategy is applied, it writes a record of the application and its context. This log is later updated with the outcome, forming the basis of the continuous learning loop.
    *   **Agent Memory DB (`agent_episodes` table):** After a decision is made, it asynchronously logs the complete decision episode, including which strategies were applied.
    *   **Chronicle Service:** Writes a high-level record of orchestration decisions for auditing purposes.
    *   **Other Services:** It triggers actions in other services via their APIs (e.g., telling the Sprint Service to create a new sprint).

---

## 6. Inter-Service Communication

The DSM microservices communicate primarily through API calls and event streams to maintain a decoupled architecture. The Project Orchestrator acts as a central coordinator, consuming data from various services to make informed decisions. With the integration of historical intelligence, its role has expanded to become an AI-augmented decision-maker.

### 6.1 API-Driven Communication

The communication for the Project Orchestrator is now driven by a "strategy-first" intelligence model. The process is divided into the core decision-making flow, a post-decision advisory review, and an asynchronous strategy evolution workflow.

#### 6.1.1 Core Decision-Making Flow (Strategy-First)

The following diagram illustrates the updated API interactions, where learned strategies are the primary source of intelligence, followed by Chronicle patterns and episode memory as fallbacks.

```mermaid
sequenceDiagram
    participant API as Orchestration API
    participant DE as Enhanced Decision Engine
    participant PE as Pattern Engine
    participant SR as Strategy Repository
    participant AgentMemory as agent_memory (DB)
    participant ER as Episode Retriever
    participant Chronicle as Chronicle Service
    participant DM as Decision Modifier

    API->>DE: POST /orchestrate/project/{id}
    DE->>DE: Generate rule-based baseline

    DE->>PE: Get intelligence recommendations
    PE->>SR: Query applicable strategies (by context)
    SR->>AgentMemory: SELECT from agent_knowledge WHERE confidence > 0.5
    AgentMemory-->>SR: Return matching strategies
    SR-->>PE: Return strategies with applicability scores

    alt High-confidence strategy found (>0.75)
        PE->>PE: Use strategy as primary recommendation
        PE->>Chronicle: Get Chronicle patterns (secondary)
        PE->>ER: Get episode patterns (tertiary)
    else No high-confidence strategy
        PE->>Chronicle: Get Chronicle patterns
        PE->>ER: Get episode patterns
        PE->>PE: Combine all sources
    end

    PE-->>DE: Return combined intelligence
    DE->>DM: Generate adjustments
    DM-->>DE: Return validated adjustments
    DE->>DE: Apply adjustments to baseline

    DE->>AgentMemory: Log STRATEGY_APPLIED event (to strategy_performance_log)

    DE-->>API: Return enhanced decision (with strategy_context)

```

#### 6.1.2 AI Agent Advisory Flow (Post-Decision)

After the core decision is finalized, the AI Agent Advisor is invoked as a non-blocking, final step to enrich the API response. This flow is controlled by a feature flag.

```mermaid
sequenceDiagram
    participant DE as Enhanced Decision Engine
    participant AA as AI Agent Advisor
    participant Ollama as Ollama Server (llama3.2)
    participant API as Orchestration API

    Note over DE,API: Post-Decision Advisory Generation

    DE->>DE: Final Decision is Ready

    alt AI Advisor Enabled
        DE->>AA: review_decision(decision_context)
        AA->>AA: Build Prompt for LLM
        AA->>Ollama: POST /api/generate (with timeout)
        Ollama-->>AA: Natural Language Response
        AA->>AA: Parse to Structured Advisory
        AA-->>DE: Advisory Response (JSON object)
        DE->>DE: Enrich API Response with Advisory
    else AI Advisor Disabled or Failed
        DE->>DE: Proceed without advisory
    end

    DE-->>API: Final Enriched API Response
```

### 6.2 Event-Driven Communication (Redis Streams)

Redis Streams are utilized for asynchronous, event-driven communication for task tracking and agent learning.

*   **`daily_scrum_events`**:
    *   **Publisher**: Sprint Service
    *   **Consumer**: Sprint Service
    *   **Event Type**: `TASK_PROGRESSED` - Indicates progress made on a specific task within a sprint.

*   **`task_update_events`**:
    *   **Publisher**: Sprint Service
    *   **Consumer**: Backlog Service
    *   **Event Type**: `TASK_UPDATED` - Notifies the Backlog Service of changes to task status or assignment.

*   **`orchestration_events`**:
    *   **Publisher**: Project Orchestration Service
    *   **Consumer**: Learning Optimizer, Chronicle Service
    *   **Event Type**: `STRATEGY_APPLIED` - Published when a learned strategy is used in a decision, triggering the learning loop.

*   **`agent_learning_events`** (NEW):
    *   **Publisher**: Strategy Evolver Service (within Project Orchestrator)
    *   **Consumer**: Chronicle Service (for audit), Monitoring Dashboard
    *   **Event Type**: `STRATEGY_EVOLVED` - Published after the daily strategy evolution process, summarizing new and updated strategies.

## 7. Database-per-Service Architecture Implementation

### 7.1 Architecture Overview

The DSM system implements a true database-per-service model with event sourcing, moving away from a monolithic, shared database towards a more scalable and decoupled microservices architecture.

#### Current State (Monolithic Database)
- Single PostgreSQL database (`dsm_db`) shared by all services
- 18 tables with cross-service foreign key dependencies
- Tight coupling at the data layer
- Single point of failure
- Direct database access across services

#### Target State (Database-per-Service)
- 4 independent databases (3 PostgreSQL + 1 Redis)
- Service-specific table ownership
- API-based inter-service communication
- Event-driven updates for progress tracking
- Complete service autonomy

### 7.2 Service Database Distributions

#### 1. Project Service Database (`project-db`)

**Domain**: Project and Team Management
**Database Type**: PostgreSQL
**Connection**: `project-service` deployment

**Tables Owned**:
- `projects` - Core project information
- `teams` - Employee/team member data
- `designations` - Job titles and experience levels
- `roles` - Job roles and responsibilities
- `project_team_mapping` - Links projects to team members
- `team_designation_mapping` - Links team members to job designations
- `team_role_mapping` - Links team members to roles
- `role_designation_mapping` - Links roles to designations
- `pto_calendar` - Paid time off tracking
- `us_holidays` - Holiday calendar

#### 2. Backlog Service Database (`backlog-db`)

**Domain**: Task and Story Management
**Database Type**: PostgreSQL
**Connection**: `backlog-service` deployment

**Tables Owned**:
- `tasks` - Individual task items
- `stories` - User stories
- `story_tasks` - Links between stories and tasks

#### 3. Sprint Service Database (`sprint-db`)

**Domain**: Sprint Management and Progress Tracking
**Database Type**: PostgreSQL
**Connection**: `sprint-service` deployment

**Tables Owned**:
- `sprints` - Sprint information
- `tasks` - Local copy of tasks for sprint management (progress tracking)
- `stories` - User stories
- `story_tasks` - Links between stories and tasks

#### 4. Chronicle Service Database (`chronicle-db`)

**Domain**: Historical Reporting, AI Agent Memory, and Notes
**Database Type**: PostgreSQL (contains two logical databases: `chronicle_db` and `agent_memory`)
**Connection**: `chronicle-service` deployment

**Tables Owned**:
- `chronicle_notes` - Primarily for Daily Scrum Reports
- `sprint_retrospectives` - Structured sprint retrospective reports
- `retrospective_action_items` - Action items for retrospectives
- `retrospective_attendees` - Attendees for retrospectives
- `agent_episodes` - Episodic memory for agent decisions
- `agent_knowledge` - Semantic memory for learned patterns and strategies
- `strategy_performance_log` - (NEW) Tracks outcomes of applied strategies for continuous learning
- `agent_working_memory` - Session-based context for active orchestrations
- `agent_memory_metrics` - Performance metrics for the memory system



### 7.3 Migration Strategy

#### Phase 1: Database Provisioning
1. Create new service databases
2. Set up database connections and credentials
3. Configure service-specific database access

#### Phase 2: Service Migration
1. Migrate data to appropriate services
2. Update service configurations
3. Remove foreign key constraints
4. Implement API-based communication

#### Phase 3: Testing and Validation
1. Test inter-service communication
2. Monitor performance and errors
3. Validate data consistency
4. Update documentation


## Appendix: Implementation Details

### Database Connection Configuration

**Project Service**:
```yaml
DATABASE_URL: postgresql://dsm_user:dsm_password@postgres-project:5432/project_db
```

**Backlog Service**:
```yaml
DATABASE_URL: postgresql://dsm_user:dsm_password@postgres-backlog:5432/backlog_db
```

**Sprint Service**:
```yaml
DATABASE_URL: postgresql://dsm_user:dsm_password@postgres-sprint:5432/sprint_db
```