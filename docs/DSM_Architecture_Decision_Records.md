# Architecture Decision Records (ADRs)

## Overview

This document contains Architecture Decision Records (ADRs) for the DSM (Digital Scrum Master) system. ADRs are short text documents that capture important architectural decisions made during the development of the system, along with their context, consequences, and rationale.

## Table of Contents
- [ADR-001: Adopt the Database-per-Service Pattern](#adr-001-adopt-the-database-per-service-pattern)
- [ADR-002: Use Redis Streams for Event-Driven Communication](#adr-002-use-redis-streams-for-event-driven-communication)
- [ADR-003: Deploy Services Using Kubernetes-Native Workflows](#adr-003-deploy-services-using-kubernetes-native-workflows)
- [ADR-004: Implement ConfigMap-Based Deployment Strategy](#adr-004-implement-configmap-based-deployment-strategy)
- [ADR-005: Hybrid Communication Model (API + Event-Driven)](#adr-005-hybrid-communication-model-api--event-driven)
- [ADR-006: Implement Comprehensive Health Check Strategy](#adr-006-implement-comprehensive-health-check-strategy)
- [ADR-007: Use FastAPI for Service Implementation](#adr-007-use-fastapi-for-service-implementation)
- [ADR-008: Implement Resource Requests and Limits](#adr-008-implement-resource-requests-and-limits)
- [ADR-009: Adopt Event Sourcing for Task Progress Tracking](#adr-009-adopt-event-sourcing-for-task-progress-tracking)
- [ADR-010: Implement Pod Disruption Budgets for Critical Services](#adr-010-implement-pod-disruption-budgets-for-critical-services)
- [ADR-011: Use Database Connection Pooling](#adr-011-use-database-connection-pooling)
- [ADR-012: Centralize Historical Data in Chronicle Service](#adr-012-centralize-historical-data-in-chronicle-service)
- [ADR-013: Implement Automated Sprint Closure and Retrospectives](#adr-013-implement-automated-sprint-closure-and-retrospectives)
- [ADR-014: Use Structured JSON Logging](#adr-014-use-structured-json-logging)
- [ADR-015: Adopt Agentic AI Orchestration Pattern](#adr-015-adopt-agentic-ai-orchestration-pattern)
- [ADR-016: Implement Multi-Replica Deployments for Critical Services](#adr-016-implement-multi-replica-deployments-for-critical-services)
- [ADR-017: Use Kubernetes CronJobs for Automated Workflows](#adr-017-use-kubernetes-cronjobs-for-automated-workflows)
- [ADR-018: Implement Event Schema Versioning](#adr-018-implement-event-schema-versioning)
- [ADR-019: Use Pydantic for Data Validation and Serialization](#adr-019-use-pydantic-for-data-validation-and-serialization)
- [ADR-020: Implement Circuit Breaker Patterns for Service Dependencies](#adr-020-implement-circuit-breaker-patterns-for-service-dependencies)
- [ADR-021: Adopt Dedicated AI Infrastructure](#adr-021-adopt-dedicated-ai-infrastructure)
- [ADR-022: Implement "Agent Brain" Database Architecture](#adr-022-implement-agent-brain-database-architecture)
- [ADR-023: Adopt Asynchronous Strategy Evolution Layer](#adr-023-adopt-asynchronous-strategy-evolution-layer)
- [Implementation Status Summary](#implementation-status-summary)
- [Summary](#summary)
- [Related Documentation](#related-documentation)

## ADR Format

Each ADR follows this standardized format:

- **ADR-XXX**: Brief title
- **Date**: When the decision was made
- **Status**: Proposed, Accepted, Deprecated, Superseded
- **Implementation Status**: Implemented, Partially Implemented, Future Consideration, Not Started
- **Context**: The situation that led to this decision
- **Decision**: The architectural decision that was made
- **Consequences**: The resulting context after applying the decision
- **Rationale**: Why this decision was made over alternatives
- **Implementation Details**: Specific details about how the decision was implemented

---

## ADR-001: Adopt the Database-per-Service Pattern

**Date**: 2024-12-19
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: The DSM system initially used a monolithic, shared PostgreSQL database (`dsm_db`) with 18 tables and cross-service foreign key dependencies. This created tight coupling at the data layer, single points of failure, and direct database access across services, limiting scalability and service autonomy. The system needed to evolve from a monolithic database architecture to support true microservices independence and enable independent scaling of services.

**Decision**: Implement a true database-per-service model where each core microservice owns its own dedicated PostgreSQL database, ensuring data isolation and service autonomy.

**Consequences**:
- **Positive**:
  - Complete service autonomy and independent scaling
  - Data isolation prevents cross-service data corruption
  - Eliminates single point of failure at the database level
  - Enables service-specific database optimizations
  - Clear data ownership boundaries
- **Negative**:
  - Increased infrastructure complexity (7 separate databases)
  - Need for eventual consistency patterns for cross-service data
  - More complex deployment and backup strategies
  - Potential data duplication for shared reference data

**Rationale**: The database-per-service pattern aligns with microservices best practices and provides the foundation for true service independence. While it increases operational complexity, the benefits of service autonomy, scalability, and resilience outweigh the costs. The system implements event-driven communication patterns to maintain data consistency across services.

**Implementation Details**:
- **Project Service Database**: `project-db` with tables for projects, teams, roles, designations, PTO calendar, and US holidays
- **Backlog Service Database**: `backlog-db` with tables for tasks, stories, and story-task relationships
- **Sprint Service Database**: `sprint-db` with tables for sprints and local task copies for sprint management
- **Chronicle Service Database**: `chronicle-db` with tables for historical reports, daily scrum notes, and sprint retrospectives
- **Project Orchestrator Service Databases**: Manages three distinct databases for its learning capabilities:
  - `agent_episodes`: Stores episodic memory (records of past decisions).
  - `agent_knowledge`: A repository for learned, versioned strategies.
  - `strategy_performance_log`: Tracks the outcomes of applied strategies.
- **Database Migration Strategy**: Implemented through Kubernetes Jobs that create databases and apply schema migrations in dependency order
- **Connection Configuration**: Each service configured with dedicated database connection strings and connection pooling

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-002: Use Redis Streams for Event-Driven Communication

**Date**: 2024-12-19
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: The system needed a reliable mechanism for asynchronous communication between services, particularly for task progress updates that occur frequently during daily scrum simulations. Direct API calls would create tight coupling and potential performance bottlenecks. The system required a solution that could handle high-volume, real-time updates while maintaining loose coupling between services.

**Decision**: Implement Redis Streams as the primary event store for asynchronous, event-driven communication, especially for task progress synchronization between services.

**Consequences**:
- **Positive**:
  - Decoupled, scalable communication between services
  - Reliable event delivery with consumer groups
  - Event history and replay capabilities
  - Improved system resilience and fault tolerance
  - Better performance for high-volume updates
- **Negative**:
  - Additional infrastructure component to manage
  - Eventual consistency model for cross-service data
  - Need for event schema versioning and migration
  - Potential message ordering complexities

**Rationale**: Redis Streams provide the reliability and scalability needed for event-driven communication while maintaining simplicity compared to more complex message brokers. The event sourcing approach enables better auditability and supports future enhancements like event replay and complex workflows.

**Implementation Details**:
- **Event Flow**: The `Sprint Service` now simulates task progress, updates its local database, and publishes `TASK_UPDATED` events to Redis Streams. The `Backlog Service` consumes these `TASK_UPDATED` events to synchronize the master backlog. The `Daily Scrum Service`'s role in this event flow is deprecated.
- **Event Schemas**: Structured JSON events with event_id, event_type, timestamp, and event_data fields
- **Consumer Groups**: Implemented for exactly-once processing and load distribution
- **Redis Configuration**: Single Redis instance with resource limits (200Mi memory, 200m CPU)
- **Event Processing**: Async event consumers in Sprint and Backlog services with error handling and acknowledgment

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-003: Deploy Services Using Kubernetes-Native Workflows

**Date**: 2024-12-19
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: The system needed a robust, scalable deployment strategy that could handle the complexity of multiple microservices, databases, and event-driven communication while providing operational visibility and automated recovery. The deployment approach needed to support both development and production environments with consistent resource management and health monitoring.

**Decision**: Adopt Kubernetes as the primary orchestration platform with native resources (Deployments, Services, CronJobs, ConfigMaps, Secrets) and implement comprehensive health checks and resource management.

**Consequences**:
- **Positive**:
  - Native Kubernetes resource management and scaling
  - Built-in service discovery and load balancing
  - Automated health checks and recovery
  - Declarative configuration management
  - Resource isolation and limits
  - Pod Disruption Budgets for high availability
- **Negative**:
  - Kubernetes learning curve for operations
  - Additional complexity in deployment manifests
  - Need for Kubernetes-specific monitoring and debugging

**Rationale**: Kubernetes provides the most mature and feature-rich platform for microservices orchestration. The native resource types ensure optimal integration with the platform's capabilities, while the declarative approach enables infrastructure as code and reproducible deployments.

**Implementation Details**:
- **Namespace**: All components deployed in dedicated `dsm` namespace
- **Deployments**: Each service deployed as Kubernetes Deployment with resource requests/limits
- **Services**: Internal service discovery via Kubernetes DNS (e.g., `project-service.dsm.svc.cluster.local`)
- **ConfigMaps/Secrets**: Configuration and credentials managed via Kubernetes native resources
- **CronJobs**: Automated workflows like daily scrum simulation and orchestrator jobs
- **Resource Management**: Explicit CPU and memory limits for all containers (e.g., 200Mi-400Mi memory, 200m-400m CPU)

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-004: Implement ConfigMap-Based Deployment Strategy

**Date**: 2024-12-19
**Status**: Accepted
**Context**: The development environment needed a deployment strategy that could work without container registries while maintaining the benefits of containerized applications. Traditional approaches required building and pushing images to registries.

**Decision**: Use ConfigMaps to distribute application code and dependencies, with initContainers setting up Python virtual environments and installing dependencies within shared emptyDir volumes.

**Consequences**:
- **Positive**:
  - Registry-less deployment suitable for development/testing
  - Fast iteration cycles without image builds
  - Version control integration for application code
  - Simplified development workflow
  - Consistent environment setup
  - Consistent environment setup
- **Negative**:
  - Larger pod specifications due to ConfigMap size limits
  - Slower pod startup due to dependency installation
  - Not suitable for production environments with high security requirements
  - Potential resource overhead from virtual environments

**Rationale**: This approach enables rapid development and testing without the overhead of container registry management. While not suitable for production, it provides an excellent development experience and can be easily replaced with traditional container images for production deployments.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-005: Hybrid Communication Model (API + Event-Driven)

**Date**: 2025-08-15
**Status**: Accepted
**Implementation Status**: In Progress

**Context**: The system's evolution toward an event-driven, agentic architecture has led to a pattern where services mix synchronous API calls with asynchronous event-based interactions. This hybrid model deviates from strict microservice principles that discourage tight runtime coupling through direct service calls. However, a full transition to event-driven, autonomous behavior is a multi-phase effort. During this transitional period, there are valid reasons to intentionally blend synchronous and asynchronous communication patterns to meet business needs while preserving delivery velocity.

**Decision**: We have chosen to embrace a hybrid communication model — combining synchronous API calls and asynchronous, event-driven workflows — as a transitional architectural strategy. This decision acknowledges current system constraints, promotes incremental modernization, and balances reliability with forward compatibility.

**Rationale**:
- Pragmatic Transition: Replacing all synchronous interactions with asynchronous equivalents in a single step is risky and time-consuming. A hybrid model allows us to modernize incrementally, focusing efforts where the benefits of decoupling are most impactful.
- Context-Appropriate Coupling: Not all service interactions require decoupling. For example, read-heavy, low-latency lookups are often best handled via direct API calls. By carefully identifying when coupling is acceptable (e.g., for stable, low-risk dependencies), we maintain system agility without unnecessary complexity.
- Enables Delivery While Supporting Evolution: New features can be shipped using existing synchronous interfaces while emitting events in parallel for asynchronous processing and observability. This dual-path model enables progressive rollout of event-driven features without blocking delivery.
- Telemetry and Observability: APIs offer immediate response visibility, while event streams support auditability and replayability. This combination improves system insight, which is critical as we transition toward agent-driven orchestration.
- Backward Compatibility: Existing consumers continue to function without immediate refactoring. New systems and agents can subscribe to events emitted alongside API calls, providing a bridge between old and new paradigms.

**Consequences**:
- The system retains some synchronous coupling, which introduces risk during outages or changes in upstream services.
- Complexity increases temporarily, as dual communication paths must be maintained and observed.
- Enables incremental refactoring of critical services into autonomous, event-driven components without halting feature development.
- Event-driven patterns can be introduced in parallel to synchronous logic, gradually taking over orchestration responsibilities.

**Implementation Details**:
- Synchronous API calls are used for immediate, request-response interactions (e.g., agent orchestration, data lookups, direct reporting to Chronicle Service).
- Asynchronous event-driven communication is implemented via Redis Streams for high-volume, eventually consistent updates (e.g., task progress synchronization using `TASK_PROGRESSED` and `TASK_UPDATED` events).
- Observability tools, including structured JSON logging and comprehensive health checks, support monitoring of both synchronous and asynchronous flows.
- The long-term vision is to transition more workflows to fully event-driven orchestration, limiting synchronous APIs to specific query patterns.

**Inter-Service Dependencies (API Calls)**:
- **Backlog Service**:
  - Calls `Project Service` to validate project existence.
- **Sprint Service**:
  - Calls `Project Service` to validate projects and fetch team data.
  - Calls `Backlog Service` to retrieve and update tasks.
  - Calls `Chronicle Service` to submit daily scrum reports.
- **Daily Scrum Service (Deprecated)**:
  - Calls `Sprint Service` to retrieve active tasks.
- **Project Orchestration Service**:
  - Calls `Project Service` to validate projects and get team data.
  - Calls `Backlog Service` to get task information.
  - Calls `Sprint Service` to manage sprints.
  - Calls `Chronicle Service` to record orchestration actions.
  - Calls `Embedding Service` to generate vector embeddings for agent memory.
  - Directly accesses its own databases (`agent_episodes`, `agent_knowledge`, `strategy_performance_log`) for learning and strategy management.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-006: Implement Comprehensive Health Check Strategy

**Date**: 2024-12-19
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: The system needed reliable health monitoring to ensure traffic is only routed to fully operational service instances and to enable automated recovery from failures. The health monitoring needed to distinguish between service process health and operational readiness including all dependencies.

**Decision**: Implement a two-tier health check strategy with `/health` (liveness) and `/health/ready` (readiness) endpoints, along with custom logging filters to reduce noise from frequent health check requests.

**Consequences**:
- **Positive**:
  - Accurate pod health status for Kubernetes
  - Comprehensive dependency checking
  - Reduced log noise from health check endpoints
  - Better operational visibility
  - Automated failure detection and recovery
- **Negative**:
  - Additional complexity in service implementation
  - Need to maintain health check logic
  - Potential for health check failures to cascade

**Rationale**: Comprehensive health checks are essential for reliable microservices operation. The two-tier approach ensures that pods are only considered ready when all critical dependencies are available, while the logging filters maintain clean, actionable logs for operators.

**Implementation Details**:
- **Liveness Probe**: `/health` endpoint returns simple `{"status": "ok"}` for process health
- **Readiness Probe**: `/health/ready` endpoint checks all dependencies (database, Redis, external services) and returns detailed JSON status
- **Kubernetes Integration**: startupProbe uses `/health/ready`, readinessProbe uses `/health`
- **Log Filtering**: Custom logging configuration suppresses Uvicorn access logs for health check endpoints
- **Dependency Checking**: Each service checks its specific dependencies (e.g., Sprint Service checks Project, Backlog, Chronicle services)

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-007: Use FastAPI for Service Implementation

**Date**: 2024-12-19
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: The system needed a modern, performant web framework that could handle the API requirements of microservices while providing excellent developer experience and automatic documentation. The framework needed to support async operations, type safety, and comprehensive API documentation.

**Decision**: Standardize on FastAPI as the web framework for all microservices, leveraging its automatic OpenAPI documentation, type safety, and high performance.

**Consequences**:
- **Positive**:
  - Automatic API documentation with OpenAPI/Swagger
  - Type safety and validation with Pydantic
  - High performance with async support
  - Excellent developer experience
  - Built-in dependency injection
  - Modern Python features and syntax
- **Negative**:
  - Learning curve for teams unfamiliar with FastAPI
  - Dependency on FastAPI ecosystem
  - Potential for over-engineering simple endpoints

**Rationale**: FastAPI provides the best balance of performance, developer experience, and features for building modern microservices APIs. The automatic documentation generation is particularly valuable for maintaining API contracts across multiple services.

**Implementation Details**:
- **Framework Version**: FastAPI with Python 3.9+ compatibility
- **Pydantic Models**: Used for request/response validation and serialization
- **Async Support**: Leveraged for database operations and external API calls
- **OpenAPI Documentation**: Automatic generation available at `/docs` endpoint
- **Error Handling**: Comprehensive HTTP exception handling with structured responses
- **Middleware**: CORS, logging, and request/response processing middleware

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-008: Implement Resource Requests and Limits

**Date**: 2024-12-19
**Status**: Accepted
**Context**: The system needed predictable performance and resource utilization to prevent resource contention and ensure fair allocation across services in the Kubernetes cluster.

**Decision**: Configure explicit CPU and memory requests and limits for all containers, including databases and application services.

**Consequences**:
- **Positive**:
  - Predictable performance and resource allocation
  - Prevention of "noisy neighbor" issues
  - Better Kubernetes scheduler decisions
  - Resource cost predictability
  - Improved cluster stability
- **Negative**:
  - Need to carefully tune resource requirements
  - Potential for resource underutilization
  - More complex capacity planning

**Rationale**: Explicit resource management is essential for production-grade Kubernetes deployments. It ensures fair resource allocation, prevents resource contention, and enables better capacity planning and cost management.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-009: Adopt Event Sourcing for Task Progress Tracking

**Date**: 2024-12-19
**Status**: Accepted
**Context**: The system needed to track task progress updates across multiple services while maintaining data consistency and providing auditability for project management activities.

**Decision**: Implement event sourcing for task progress tracking using Redis Streams, where task progress events are published and consumed by relevant services to maintain eventually consistent state.

**Consequences**:
- **Positive**:
  - Complete audit trail of task progress changes
  - Decoupled service communication
  - Event replay capabilities for debugging
  - Scalable event processing
  - Clear separation of event publishing and consumption
- **Negative**:
  - Eventual consistency model
  - Need for event schema versioning
  - Potential for event processing failures
  - More complex debugging of state issues

**Rationale**: Event sourcing provides excellent auditability and enables scalable, decoupled communication between services. The eventual consistency model is acceptable for task progress tracking, and the benefits of complete audit trails and event replay capabilities outweigh the complexity costs.

**Implementation Details**:
- **Event Sourcing**: The `Sprint Service` simulates task progress and publishes `TASK_UPDATED` events to Redis Streams. These events are consumed by relevant services (e.g., `Backlog Service`) to maintain eventually consistent state. The `Daily Scrum Service`'s role in publishing task progress events is deprecated.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-010: Implement Pod Disruption Budgets for Critical Services

**Date**: 2024-12-19
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: Critical services like the Sprint Service needed protection against voluntary disruptions (updates, maintenance) to ensure continuous availability during cluster operations. The system required protection against accidental service disruption during Kubernetes cluster maintenance and updates.

**Decision**: Implement Pod Disruption Budgets (PDBs) for critical services to maintain a minimum number of available replicas during voluntary disruptions.

**Consequences**:
- **Positive**:
  - Enhanced service availability during maintenance
  - Protection against accidental service disruption
  - Better SLA guarantees
  - Improved user experience during updates
  - Better resource utilization
- **Negative**:
  - Slower deployment updates due to rolling update constraints
  - More complex deployment planning
  - Potential for update failures if PDB constraints cannot be met

**Rationale**: High availability is critical for production systems. PDBs provide a safety mechanism that prevents accidental service disruption during routine maintenance and updates, ensuring continuous operation for end users.

**Implementation Details**:
- **Sprint Service PDB**: Configured with `minAvailable: 1` to ensure at least one replica is always available
- **Multi-Replica Deployment**: Sprint Service deployed with multiple replicas to support PDB requirements
- **PDB Configuration**: Applied via `sprint-service-pdb.yml` manifest
- **Rolling Updates**: Kubernetes respects PDB constraints during deployment updates
- **High Availability**: Ensures Sprint Service remains available during cluster maintenance

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-011: Use Database Connection Pooling

**Date**: 2024-12-19
**Status**: Accepted
**Context**: The microservices needed efficient database connection management to handle concurrent requests while minimizing resource overhead and connection establishment latency.

**Decision**: Implement database connection pooling using psycopg2 connection pools for all PostgreSQL-based services to optimize database connections and improve performance.

**Consequences**:
- **Positive**:
  - Reduced connection establishment overhead
  - Better resource utilization
  - Improved response times
  - Connection reuse across requests
  - Better handling of connection limits
- **Negative**:
  - Additional complexity in connection management
  - Need to tune pool sizes appropriately
  - Potential for connection leaks if not properly managed

**Rationale**: Database connection pooling is essential for microservices performance. It significantly reduces the overhead of establishing new database connections for each request and enables better resource utilization across the system.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-012: Centralize Historical Data in Chronicle Service

**Date**: 2024-12-19
**Status**: Accepted
**Context**: The system needed a centralized location for storing historical data like daily scrum reports and sprint retrospectives, while maintaining clear data ownership and enabling comprehensive reporting.

**Decision**: Create a dedicated Chronicle Service with its own database to store all historical reports and notes, including daily scrum reports and sprint retrospectives.

**Consequences**:
- **Positive**:
  - Centralized historical data management
  - Clear separation of operational and historical data
  - Comprehensive reporting capabilities
  - Data retention and archival policies
  - Audit trail for project management activities
- **Negative**:
  - Additional service to maintain
  - Potential for data duplication
  - Need for data synchronization from operational services

**Rationale**: Centralizing historical data provides better organization and enables comprehensive reporting and analytics. The Chronicle Service acts as a dedicated data warehouse for project management activities, separate from operational data stores.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-013: Implement Automated Sprint Closure and Retrospectives

**Date**: 2024-12-19
**Status**: Accepted
**Context**: The system needed to automate the sprint closure process, including handling uncompleted tasks and generating retrospective reports, to reduce manual intervention and ensure consistent process execution.

**Decision**: Implement automated sprint closure workflows that move uncompleted tasks back to the backlog and generate structured retrospective reports stored in the Chronicle Service.

**Consequences**:
- **Positive**:
  - Reduced manual intervention
  - Consistent sprint closure process
  - Automated task management
  - Structured retrospective documentation
  - Better process compliance
- **Negative**:
  - Less flexibility in sprint closure decisions
  - Potential for automated decisions that don't match business needs
  - Need to handle edge cases and exceptions

**Rationale**: Automation reduces manual overhead and ensures consistent process execution. The structured approach to sprint closure and retrospectives provides better documentation and enables data-driven improvements to the development process.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-014: Use Structured JSON Logging

**Date**: 2024-12-19
**Status**: Accepted
**Context**: The system needed consistent, machine-readable logging across all services to enable effective monitoring, debugging, and log analysis in a distributed environment.

**Decision**: Implement structured JSON logging for all services with consistent log formats and custom filters to reduce noise from health check endpoints.

**Consequences**:
- **Positive**:
  - Machine-readable logs for automated analysis
  - Consistent log format across services
  - Better log aggregation and search capabilities
  - Reduced log noise from health checks
  - Improved debugging and troubleshooting
- **Negative**:
  - Less human-readable log output
  - Need for JSON log parsing tools
  - Potential for log volume increase due to structured format

**Rationale**: Structured logging is essential for effective monitoring and debugging in distributed systems. JSON format enables automated log analysis and provides consistent, searchable logs across all services while maintaining readability through proper tooling.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-015: Adopt Agentic AI Orchestration Pattern

**Date**: 2024-12-19
**Status**: Accepted
**Implementation Status**: Partially Implemented
**Context**: The architectural vision for the system centers around Agentic AI — autonomous agents capable of making decisions, triggering actions, and self-orchestrating workflows. This vision emphasizes intelligent autonomy, event-driven design, and minimal manual orchestration.
While some workflows still rely on Kubernetes CronJobs triggering direct service calls, significant progress has been made in consolidating logic into services (e.g., the daily scrum orchestration is now fully handled by the `Sprint Service` triggered by a simplified CronJob). This reduces manual orchestration and moves closer to the desired autonomous model, but a gap between the desired architecture and the current operational model still exists for other workflows.

**Decision**: We have chosen to initially implement orchestration using Kubernetes CronJobs, while laying the groundwork for a future transition to autonomous agent-based orchestration. The current approach provides a stable and known environment for managing scheduled tasks and services.
The architecture will continue evolving toward event-driven patterns and more loosely coupled services to align with the long-term goal of Agentic AI.

**Consequences**:
- There is a short-term architectural inconsistency between the system's vision and its implementation.
- The use of Kubernetes CronJobs introduces manual orchestration and tight coupling between services.
- Future refactoring will be necessary to replace static job scheduling with agent-based, autonomous behavior.

**Rationale**:
- Kubernetes provides a robust and maintainable environment for orchestration, allowing faster initial delivery.
- This phased approach allows the team to deliver value incrementally while validating architectural choices.

**Implementation Details**:
- For workflows like daily scrum, the Kubernetes CronJob now triggers a single endpoint on the `Sprint Service`, which encapsulates the entire process. This simplifies the CronJob's role and reduces direct service call orchestration from the job itself.
- Other jobs may still trigger scheduled workflows via direct API calls, but the overall trend is towards consolidating logic within services.
- Services communicate synchronously in some cases, with plans to evolve toward event-driven communication (e.g., via pub/sub).
- Monitoring and observability are implemented to track job execution, serving as a proxy for future agent telemetry.
- Future iterations will introduce agent-based decision-making modules, with agents subscribing to events and autonomously initiating tasks.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-016: Implement Multi-Replica Deployments for Critical Services

**Date**: 2024-12-19
**Status**: Accepted
**Context**: Critical services needed high availability and fault tolerance to ensure continuous operation even when individual service instances fail.

**Decision**: Deploy critical services like the Sprint Service with multiple replicas and implement proper load balancing and health checking to ensure high availability.

**Consequences**:
- **Positive**:
  - Improved service availability and fault tolerance
  - Better load distribution
  - Graceful handling of instance failures
  - Enhanced user experience
  - Better resource utilization
- **Negative**:
  - Increased resource consumption
  - More complex state management
  - Potential for session affinity issues
  - Higher operational complexity

**Rationale**: High availability is essential for production systems. Multi-replica deployments provide fault tolerance and ensure continuous service availability even when individual instances fail, improving overall system reliability.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-017: Use Kubernetes CronJobs for Automated Workflows

**Date**: 2024-12-19
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: The system needed to automate recurring processes like daily scrum simulations without requiring external scheduling systems or manual intervention.

**Decision**: Use Kubernetes CronJobs to schedule and execute automated workflows like daily scrum simulations, leveraging the native Kubernetes scheduling capabilities.

**Consequences**:
- **Positive**:
  - Native Kubernetes integration
  - Declarative scheduling configuration
  - Built-in retry and failure handling
  - Consistent with overall deployment strategy
  - No external scheduling dependencies
- **Negative**:
  - Limited to Kubernetes cluster scheduling
  - Less flexible than external scheduling systems
  - Potential for scheduling conflicts
  - Need to manage CronJob lifecycle

**Rationale**: Using Kubernetes CronJobs maintains consistency with the overall deployment strategy and eliminates dependencies on external scheduling systems. The native integration provides better observability and management within the Kubernetes ecosystem.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-018: Implement Event Schema Versioning

**Date**: 2024-12-19
**Status**: Accepted
**Implementation Status**: Future Consideration
**Context**: As the system evolves, event schemas will need to change while maintaining backward compatibility and ensuring reliable event processing across service versions. The current event schemas are stable but will need versioning as the system matures and new features are added.

**Decision**: Design event schemas with versioning support and implement strategies for handling schema evolution and backward compatibility.

**Consequences**:
- **Positive**:
  - Backward compatibility during schema evolution
  - Gradual migration of event consumers
  - Reduced risk during system updates
  - Better long-term maintainability
  - Support for multiple schema versions
- **Negative**:
  - Increased complexity in event processing
  - Need for schema migration strategies
  - Potential for version proliferation
  - More complex testing requirements

**Rationale**: Event schema versioning is essential for long-term system evolution. It enables safe schema changes and ensures that event consumers can be updated gradually without breaking the overall system.

**Implementation Details**:
- **Current State**: Basic event schemas without versioning (event_id, event_type, timestamp, event_data)
- **Future Requirements**: Schema version field, migration strategies, backward compatibility handling
- **Planned Approach**: Version field in event metadata, consumer-side schema validation
- **Migration Strategy**: Gradual rollout with support for multiple schema versions
- **Testing Strategy**: Schema compatibility testing and validation tools

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-019: Use Pydantic for Data Validation and Serialization

**Date**: 2024-12-19
**Status**: Accepted
**Context**: The system needed robust data validation and serialization across API boundaries and event schemas to ensure data integrity and provide clear error messages.

**Decision**: Standardize on Pydantic for data validation, serialization, and API model definitions across all services.

**Consequences**:
- **Positive**:
  - Automatic data validation and error handling
  - Type safety and IDE support
  - Automatic API documentation generation
  - Consistent data models across services
  - Clear error messages for invalid data
- **Negative**:
  - Learning curve for Pydantic syntax
  - Potential performance overhead for complex validations
  - Dependency on Pydantic ecosystem
  - Need to maintain model definitions

**Rationale**: Pydantic provides excellent data validation and serialization capabilities that integrate well with FastAPI. The automatic validation and clear error messages improve developer experience and reduce data-related bugs.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-020: Implement Circuit Breaker Patterns for Service Dependencies

**Date**: 2024-12-19
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: The system needed to handle failures in service dependencies gracefully to prevent cascading failures and maintain system stability during partial outages. While basic error handling exists, more sophisticated resilience patterns are needed for production readiness.

**Decision**: Implement circuit breaker patterns for inter-service communication to prevent cascading failures and provide graceful degradation when dependencies are unavailable.

**Consequences**:
- **Positive**:
  - Prevention of cascading failures
  - Graceful degradation during outages
  - Better system resilience
  - Improved user experience during failures
  - Automatic recovery when dependencies are restored
- **Negative**:
  - Increased complexity in service communication
  - Need to handle partial failure states
  - Potential for data inconsistency during circuit breaker states
  - More complex testing scenarios

**Rationale**: Circuit breakers are essential for building resilient microservices. They prevent cascading failures and enable graceful degradation, ensuring that the system remains operational even when some dependencies are unavailable.

**Implementation Details**:
- **Current State**: The circuit breaker pattern is fully implemented in critical services to protect against cascading failures.
- **Implementations**:
  - **Backlog Service**: Protects its dependency on the Project Service.
  - **Sprint Service**: A multi-service breaker protects dependencies on the Project, Backlog, and Chronicle services.
  - **Project Orchestrator Service**: A comprehensive multi-service breaker protects all its downstream dependencies.
- **Configuration**: Standardized and configurable failure thresholds and recovery timeouts.
- **Monitoring**: Circuit breaker states are exposed via health check endpoints for real-time operational visibility.
- **Testing Strategy**: Failure injection testing has been used to validate circuit breaker behavior.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-021: Adopt Dedicated AI Infrastructure

**Date**: 2025-11-05
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: The evolution of the Project Orchestrator into a "Learning Agent" required advanced AI capabilities like semantic search (for finding similar past decisions) and natural language processing (for the AI Advisor). Relying on external, cloud-based AI services would introduce external dependencies, potential costs, and data privacy concerns. The system needed a self-contained, in-cluster solution.
**Decision**: Implement a dedicated AI infrastructure layer within the Kubernetes cluster using an `Ollama Server` to host and serve local AI models. Create a lightweight `Embedding Service` to act as a specialized proxy for generating vector embeddings and provide a simple API for the AI Agent Decision Advisor to interact with an LLM.
**Consequences**:
- **Positive**:
  - Decouples AI model serving from core application logic.
  - Avoids dependencies on external, potentially costly, cloud AI APIs.
  - Keeps all data within the cluster, enhancing security and privacy.
  - Provides a centralized and scalable point for managing AI model inference.
  - Stateless `Embedding Service` can be easily scaled horizontally.
- **Negative**:
  - Adds new infrastructure components (`Ollama Server`, `Embedding Service`) to manage and monitor.
  - Requires cluster resources (CPU, memory, potentially GPU) to run the AI models effectively.
  - The performance and quality of the AI capabilities are dependent on the chosen local models.
**Rationale**: This approach provides a robust, secure, and cost-effective foundation for the agent's AI capabilities. It aligns with the system's Kubernetes-native design and provides the flexibility to swap out models in the future without impacting the services that consume them.
**Implementation Details**:
- An `Ollama Server` is deployed as a Kubernetes Deployment to run local AI models (e.g., `mxbai-embed-large` for embeddings, `llama3.2:latest` for the LLM).
- A stateless `Embedding Service` is deployed, acting as a proxy to the Ollama server.
- The `Project Orchestration Service` communicates with the `Embedding Service` via HTTP API calls.
- Health checks are implemented in the `Embedding Service` to monitor the availability of the Ollama server.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-022: Implement "Agent Brain" Database Architecture

**Date**: 2025-11-05
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: As the Project Orchestrator evolved into a Learning Agent, it needed a persistent, structured way to store its experiences (episodic memory), learned knowledge (semantic memory), and performance data to enable continuous improvement. A single, monolithic database table would not be sufficient to separate these distinct types of memory.
**Decision**: Implement a three-part "Agent Brain" using dedicated PostgreSQL databases with the `pgvector` extension enabled. The three databases are: `agent_episodes` for storing records of past decisions with vector embeddings; `agent_knowledge` for storing versioned, reusable strategies; and `strategy_performance_log` to track the real-world outcomes of applied strategies.
**Consequences**:
- **Positive**:
  - Formal separation of different memory types (experience vs. learned knowledge) enables a clear learning workflow.
  - Using `pgvector` within the existing PostgreSQL stack enables powerful vector similarity search without adding a new database technology.
  - The dedicated `strategy_performance_log` provides the necessary data for a closed-loop learning system.
  - Clear data ownership for the Project Orchestrator service.
- **Negative**:
  - Increases the number of databases to manage, back up, and monitor.
  - Introduces a dependency on the `pgvector` extension.
  - Adds complexity to the data model for the agent.
**Rationale**: This architecture provides a sophisticated and scalable foundation for the agent's memory and learning capabilities. It allows the agent to not only remember what it did but also to learn from it and codify that learning into reusable knowledge, which is a cornerstone of an advanced agentic system.
**Implementation Details**:
- Three new PostgreSQL databases are created: `agent_episodes`, `agent_knowledge`, and `strategy_performance_log`.
- The `pgvector` extension is enabled in the `agent_episodes` database to support vector columns.
- The `Project Orchestration Service` is the sole owner of these databases.
- A dedicated `AgentMemoryClient` within the orchestrator handles all interactions with these databases.

[Back to Top](#architecture-decision-records-adrs)

---

## ADR-023: Adopt Asynchronous Strategy Evolution Layer

**Date**: 2025-11-05
**Status**: Accepted
**Implementation Status**: Implemented
**Context**: The Learning Agent needed a mechanism to analyze its past performance and generate new, improved decision-making strategies. Performing this computationally intensive analysis within the synchronous, user-facing orchestration API would lead to unacceptable latency and poor user experience.
**Decision**: Implement an asynchronous "Strategy Evolution Layer" that operates in the background. This process is orchestrated by a daily Kubernetes CronJob (`Strategy Evolver Service`) which triggers a workflow to analyze successful episodes, extract common patterns, generate formal strategies, and store them in the `agent_knowledge` database.
**Consequences**:
- **Positive**:
  - Decouples the learning process from the real-time decision-making process, ensuring the orchestration API remains fast and responsive.
  - Allows the agent to perform complex, long-running analysis without impacting users.
  - The CronJob-based approach is reliable and aligns with the system's Kubernetes-native design.
  - Enables a continuous, automated self-improvement loop for the agent.
- **Negative**:
  - Learnings are not real-time; there is a delay (e.g., up to 24 hours) before new strategies are generated and available.
  - Adds another CronJob to the system that needs to be monitored.
  - Increases the complexity of the overall agent architecture.
**Rationale**: An asynchronous learning loop is a common and effective pattern in agentic systems. It provides a clear separation of concerns between "acting" and "learning," ensuring that the agent can be both performant in its immediate tasks and capable of long-term improvement.
**Implementation Details**:
- A Kubernetes CronJob is configured to run daily.
- The job triggers the `Strategy Evolver Service` within the `Project Orchestration Service`.
- This service queries the `agent_episodes` and `strategy_performance_log` databases.
- It uses a `Pattern Extractor` to find successful patterns and a `Strategy Generator` to create new strategies.
- New and updated strategies are saved to the `agent_knowledge` database via the `Strategy Repository`.

[Back to Top](#architecture-decision-records-adrs)

---

## Implementation Status Summary

### Currently Implemented (21 ADRs)
- **ADR-001**: Database-per-Service Pattern - Fully implemented with 7 dedicated PostgreSQL databases across 5 services.
- **ADR-002**: Redis Streams for Event-Driven Communication - Implemented with TASK_PROGRESSED/TASK_UPDATED event flow
- **ADR-003**: Kubernetes-Native Workflows - Fully implemented with all native Kubernetes resources
- **ADR-004**: ConfigMap-Based Deployment Strategy - Implemented across all services with initContainers
- **ADR-005**: Hybrid Communication Pattern - Implemented with API calls and Redis Streams
- **ADR-006**: Comprehensive Health Check Strategy - Implemented with two-tier health checks and log filtering
- **ADR-007**: FastAPI for Service Implementation - Implemented across all microservices
- **ADR-008**: Resource Requests and Limits - Implemented for all containers and databases
- **ADR-009**: Event Sourcing for Task Progress Tracking - Implemented with Redis Streams
- **ADR-010**: Pod Disruption Budgets - Implemented for Sprint Service with PDB configuration
- **ADR-011**: Database Connection Pooling - Implemented with psycopg2 connection pools
- **ADR-012**: Centralized Historical Data - Implemented with Chronicle Service and dedicated database
- **ADR-013**: Automated Sprint Closure - Implemented with automated workflows and retrospective generation
- **ADR-014**: Structured JSON Logging - Implemented with structured logging and health check filtering
- **ADR-016**: Multi-Replica Deployments - Implemented for Sprint Service with multiple replicas
- **ADR-017**: Kubernetes CronJobs - Basic implementation exists, advanced scheduling features planned
- **ADR-019**: Pydantic for Data Validation - Implemented for API models, extended validation planned
- **ADR-020**: Circuit Breaker Patterns - Implemented in Backlog, Sprint, and Project Orchestrator services.
- **ADR-021**: Adopt Dedicated AI Infrastructure - Implemented with Ollama and a dedicated Embedding Service.
- **ADR-022**: Implement "Agent Brain" Database Architecture - Implemented with three dedicated databases for agent memory.
- **ADR-023**: Adopt Asynchronous Strategy Evolution Layer - Implemented via a daily Kubernetes CronJob.

### Partially Implemented (1 ADR)
- **ADR-015**: Agentic AI Orchestration Pattern - Basic orchestrator job implemented, advanced AI features planned

### Future Considerations (1 ADR)
- **ADR-018**: Event Schema Versioning - Not yet implemented, needed for long-term evolution

## Summary

These Architecture Decision Records document the key architectural decisions that have shaped the DSM system. Each decision was made with careful consideration of the trade-offs between complexity, performance, maintainability, and operational requirements.

The decisions collectively establish a robust, scalable, and maintainable microservices architecture that supports intelligent, agent-driven project management while maintaining high availability and operational excellence.

**Current System State**: The DSM system is fully functional with 22 out of 23 architectural decisions implemented or partially implemented. The core microservices architecture is complete and operational, with advanced features like AI orchestration and resilience patterns planned for future iterations.

## Related Documentation

- **[DSM Architecture Overview](DSM_Architecture_Overview.md)** - Comprehensive system architecture documentation
- **[DSM Data Architecture](DSM_Data_Architecture.md)** - Detailed data models and database design
- **[DSM Service Specifications](DSM_Service_Specifications.md)** - API specifications and service implementations
- **[DSM Deployment & Operations](DSM_Deployment_Operations.md)** - Deployment procedures and operational guidance
