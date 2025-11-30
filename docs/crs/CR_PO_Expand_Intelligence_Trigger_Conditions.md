# CR: PO - Expand Intelligence Triggers to Active Sprints

## Overview

This CR addresses a significant functional limitation in the Project Orchestrator's intelligence system: decision modifications are only triggered during **new sprint creation**. This means that for the entire duration of an active sprint, the system operates purely on its rule-based logic, and no intelligence-driven adjustments can be made. This severely limits the feature's potential impact, as opportunities for mid-sprint course correction are missed.

The objective of this CR is to expand the intelligence pipeline to analyze and propose adjustments for **active, ongoing sprints**. This will transform the orchestrator from a simple sprint planner into a more dynamic, proactive agent that can respond to changing conditions throughout the sprint lifecycle.

## Goals

*   **Goal 1**: Re-architect the `EnhancedDecisionEngine` to analyze the state of active sprints, not just plan new ones.
*   **Goal 2**: Define and implement a new set of intelligence-driven adjustments applicable to ongoing sprints (e.g., recommend scope reduction, flag at-risk tasks, suggest early sprint termination).
*   **Goal 3**: Update the orchestration API and decision audit trail to support and track these new mid-sprint interventions.
*   **Goal 4**: Ensure the system can differentiate between sprint planning and sprint management contexts, applying the correct logic for each.

## Current State Analysis

*   **Current Behavior**: The intelligence pipeline is only invoked when `create_new_sprint` is true. If an active sprint is found, the intelligence-related components are bypassed.
*   **Dependencies**: This change will affect the `EnhancedDecisionEngine`, `DecisionModifier`, and `DecisionAuditor`.
*   **Gaps/Issues**: The current implementation provides no intelligence value for the vast majority of a project's lifecycle (i.e., while a sprint is active). This is a major missed opportunity for proactive course correction.
*   **Configuration**: The system is configured for `intelligence_enhanced` mode, but this mode is effectively dormant during an active sprint.

## Proposed Solution

The solution requires a significant enhancement of the `EnhancedDecisionEngine`. A new logic path will be created to handle the `active_sprint_found` scenario. This path will invoke a new set of functions in the `DecisionModifier` designed to analyze in-progress sprint data (e.g., task progress, completion velocity) and generate relevant recommendations.

### Key Components

*   **Enhanced Decision Engine (`enhanced_decision_engine.py`)**: Will be updated with a new conditional logic branch to handle active sprints.
*   **Decision Modifier (`decision_modifier.py`)**: A new set of functions will be added, such as `generate_active_sprint_adjustments`, which will contain logic for mid-sprint analysis.
*   **New Adjustment Types**: New Pydantic models will be created to represent mid-sprint recommendations (e.g., `ActiveSprintAdjustment`).

### Architecture Changes

This represents a significant evolution of the service's business logic. The core architectural pattern remains the same (perceive, reason, act), but the "reason" phase will become more complex and context-aware, capable of handling multiple project states.

## API Changes

### Modified Endpoints

*   **`POST /orchestrate/project/{project_id}`**
    *   **Changes**: The `decisions` object in the response will now include a new `active_sprint_recommendations` field when an active sprint is being analyzed.
    *   **Backward Compatibility**: Yes, this is an additive change.
    *   **Example Response (New Structure for Active Sprint)**:
        ```json
        {
          "project_id": "TEST-001",
          "analysis": { "active_sprints": 1, ... },
          "decisions": {
            "create_new_sprint": false,
            "reasoning": "Active sprint TEST-001-S02 analyzed. Intelligence recommends scope reduction due to low velocity.",
            "decision_source": "intelligence_enhanced",
            "intelligence_adjustments": {
              "active_sprint_recommendations": {
                "recommendation_type": "SCOPE_REDUCTION",
                "details": "Team velocity is 35% below forecast. Recommend moving 2 tasks back to backlog to ensure sprint success.",
                "confidence": 0.90,
                "tasks_to_move": ["TASK-123", "TASK-124"]
              }
            }
          },
          "actions_taken": ["Flagged sprint TEST-001-S02 for review with scope reduction recommendation."]
        }
        ```

## Detailed Implementation Plan

### Phase 1: Engine and Modifier Enhancements
*   **Status**: ⏹️ Pending
*   **Step 1.1: Update Enhanced Decision Engine**
    *   **Action**: Add a new logic path to `make_orchestration_decision` that is executed when an active sprint is detected. This path will call the new active sprint analysis functions.
    *   **File**: `enhanced_decision_engine.py`
    *   **Validation**: The new code path is covered by unit tests.
*   **Step 1.2: Implement Active Sprint Adjustments**
    *   **Action**: Create new functions in `decision_modifier.py` to analyze data from an active sprint (e.g., task burndown, velocity vs. forecast) and generate actionable recommendations.
    *   **File**: `intelligence/decision_modifier.py`
    *   **Validation**: Unit tests confirm that given certain sprint states, the correct recommendations are generated.

### Phase 2: API and Audit Trail Integration
*   **Status**: ⏹️ Pending
*   **Step 2.1: Update API Response Model**
    *   **Action**: Add the `active_sprint_recommendations` field to the `EnhancedDecision` Pydantic model.
    *   **File**: `models.py`
    *   **Validation**: API schema is updated.
*   **Step 2.2: Enhance Decision Auditor**
    *   **Action**: Update the `DecisionAuditor` to correctly log these new types of mid-sprint recommendations.
    *   **File**: `intelligence/decision_auditor.py`
    *   **Validation**: The audit trail correctly stores and displays active sprint recommendations.

## Success Criteria

*   The Project Orchestrator analyzes active sprints and generates intelligence-driven recommendations.
*   At least two new types of mid-sprint adjustments (e.g., scope reduction, risk flagging) are successfully implemented.
*   The orchestration API response correctly includes the `active_sprint_recommendations` when applicable.
*   The decision audit trail accurately records all mid-sprint interventions.

## CR Status: ⏹️ PLANNED
