# DSM (Digital Scrum Master) Project Roadmap

## 1. Vision & Strategic Direction

The vision for the DSM project is to evolve from a sophisticated SDLC simulation into a fully autonomous, multi-persona agentic system that intelligently and collaboratively manages the entire software development lifecycle. The system will not only automate Agile ceremonies but also learn, adapt, and optimize its strategies over time, effectively creating a digital representation of a high-performing Agile team.

This roadmap outlines the key themes and features that will drive this evolution, focusing on enhancing agent intelligence, deepening the simulation's realism, and advancing the system's architectural maturity.

## 2. Recently Completed Milestones (Q3-Q4 2025)

The project has recently achieved significant milestones, establishing a robust foundation for future agentic capabilities:

-   **✅ Agent Strategy Evolution Layer**: The Project Orchestrator can now autonomously learn from its experiences, extracting successful patterns to create, refine, and apply its own decision-making strategies.
-   **✅ AI Agent Decision Advisor**: Integration of a local LLM to provide non-blocking, natural-language summaries and recommendations for orchestration decisions, enhancing transparency.
-   **✅ Episodic Memory Integration**: The agent's decision-making pipeline is now fully integrated with its episodic memory, allowing it to retrieve and reason from past experiences using vector similarity search.
-   **✅ Foundational Agent Memory & AI Infrastructure**: Deployed the core AI infrastructure, including the `agent_memory` database with `pgvector`, the Embedding Service, and the Ollama LLM server.
-   **✅ Automated CronJob Lifecycle Management**: The orchestrator now features self-healing capabilities, automatically creating, managing, and deleting Kubernetes CronJobs for daily scrums.
-   **✅ System-Wide Resilience**: Implemented comprehensive circuit breaker patterns across all critical services (Project Orchestrator, Sprint Service, Backlog Service) to ensure high availability and graceful degradation.

## 3. Future Roadmap

The future development of the DSM project is organized around four key themes:

### Theme 1: Enhanced Agent Intelligence & Autonomy

This theme focuses on evolving the Project Orchestrator from a learning agent into a predictive and more autonomous coordinator.

| Feature | Description | Priority | Target |
| :--- | :--- | :--- | :--- |
| **Predictive Analytics & Velocity Calculation** | The agent will calculate team velocity based on historical sprint data. This will be used to predict sprint capacity, warn against overcommitment, and provide data-driven forecasts. | High | Q1 2026 |
| **Skills-Based Task Assignment** | Introduce a `skills` attribute for team members and tasks. The agent will use this data to make more intelligent, realistic, and optimized task assignments during sprint planning. | High | Q1 2026 |
| **Multi-Persona Agent Integration** | Begin the evolution towards a multi-agent system where different AI personas (e.g., "Product Owner," "QA Engineer") collaborate. This will start with defining roles and communication protocols. | Medium | Q2 2026 |
| **Hybrid Decision Blending** | Implement the planned `hybrid` decision mode in the Project Orchestrator, allowing for more advanced, weighted blending of rule-based logic, learned strategies, and real-time analytics. | Medium | Q2 2026 |

### Theme 2: Deeper SDLC Simulation & Realism

This theme is centered on adding more complexity and realism to the simulated project environment.

| Feature | Description | Priority | Target |
| :--- | :--- | :--- | :--- |
| **Task Dependency Management** | Add a `depends_on` field to tasks. The agent will need to parse these dependencies to identify risks, suggest task sequencing, and prevent blockers during sprint planning. | High | Q1 2026 |
| **Proactive Availability Adjustments** | Enhance the agent's awareness of team availability. Instead of just warning about PTO/holidays, the agent will proactively adjust sprint capacity and task assignments based on the team's calendar. | Medium | Q2 2026 |

### Theme 3: Architectural Evolution & Scalability

This theme focuses on maturing the system's underlying architecture to support more complex features and ensure long-term scalability.

| Feature | Description | Priority | Target |
| :--- | :--- | :--- | :--- |
| **Full Event-Sourcing Implementation** | Transition from the current hybrid event model to a full event-sourcing pattern for key services. This will provide a complete, auditable log of all state changes and enable more complex state reconstruction and analysis. See **Detailed Roadmap:** [DSM_Pragmatic_Event_Design.md](DSM_Pragmatic_Event_Design.md)  for event-first architecture evolution| High | Q2 2026 |
| **Cross-Service Sagas** | Implement the Saga pattern for complex, multi-service workflows that require transactional consistency, such as a full project onboarding sequence that spans multiple services. | Medium | Q3 2026 |
| **CQRS Pattern Implementation** | For services with increasingly complex query requirements (like the Chronicle or Project Orchestrator), separate the read and write models using CQRS to optimize performance, scalability, and maintainability. | Medium | Q3 2026 |
| **Kubernetes Auto-scaling** | Implement Horizontal Pod Autoscalers (HPAs) for all stateless services, allowing the system to dynamically scale based on real-time CPU and memory usage. | Low | Q4 2026 |

### Theme 4: Operational Excellence & Observability

This theme is dedicated to improving the operational robustness, monitoring, and maintainability of the DSM ecosystem.

| Feature | Description | Priority | Target |
| :--- | :--- | :--- | :--- |
| **Advanced Observability** | Enhance monitoring to track key application-level metrics, such as event processing latency, database connection pool saturation, and inter-service API call performance. Create dedicated Grafana dashboards for these metrics. | Medium | Q2 2026 |
| **Complete Deprecation of Daily Scrum Service** | Finalize the removal of the deprecated Daily Scrum Service by deleting all related Kubernetes manifests, Docker images, and any remaining code references to simplify the architecture. | High | Q1 2026 |
