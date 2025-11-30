import os
import httpx
import structlog
from fastapi import HTTPException
from typing import Dict, Any, List
from circuit_breaker import CircuitBreaker, CircuitBrokenError

logger = structlog.get_logger()

# Configure individual circuit breakers for each service
project_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5,  # Open if 50% of calls fail
    response_time=10, # Monitor failures within a 10-second window
    exceptions=[Exception], # Count these exceptions as failures
    broken_time=30    # Stay open for 30 seconds before attempting recovery
)

backlog_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5,
    response_time=10,
    exceptions=[Exception],
    broken_time=30
)

sprint_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5,
    response_time=10,
    exceptions=[Exception],
    broken_time=30
)

chronicle_service_circuit_breaker = CircuitBreaker(
    error_ratio=0.5,
    response_time=10,
    exceptions=[Exception],
    broken_time=30
)

class ServiceClient:
    def __init__(self, base_url: str, service_name: str):
        self.base_url = base_url
        self.service_name = service_name
        self.client = httpx.AsyncClient()

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()  # Raise an exception for 4xx or 5xx status codes
            try:
                return response.json()
            except httpx.DecodingError:
                logger.error(
                    "Failed to decode JSON response from service",
                    service=self.service_name,
                    url=url,
                    method=method,
                    status_code=response.status_code,
                    response_text=response.text,
                )
                # Return an empty dict to prevent the 'str' object has no attribute 'get' error
                return {}
        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error during service request",
                service=self.service_name,
                url=url,
                method=method,
                status_code=e.response.status_code,
                response_text=e.response.text,
                error=str(e)
            )
            raise HTTPException(status_code=e.response.status_code, detail=f"{self.service_name} error: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(
                "Network error during service request",
                service=self.service_name,
                url=url,
                method=method,
                error=str(e)
            )
            raise HTTPException(status_code=503, detail=f"Could not connect to {self.service_name}: {e}")

class ProjectServiceClient(ServiceClient):
    def __init__(self):
        super().__init__(
            base_url=os.environ.get("PROJECT_SERVICE_URL", "http://project-service.dsm.svc.cluster.local"),
            service_name="Project Service"
        )

    async def get_project(self, project_id: str) -> Dict[str, Any]:
        async with project_service_circuit_breaker.context():
            return await self._make_request("GET", f"/projects/{project_id}")

    async def get_team_members(self, project_id: str) -> List[Dict[str, Any]]:
        async with project_service_circuit_breaker.context():
            return await self._make_request("GET", f"/projects/{project_id}/team-members")

    async def check_team_availability(self, project_id: str, start_date: str, end_date: str) -> Dict[str, Any]:
        async with project_service_circuit_breaker.context():
            return await self._make_request("GET", f"/projects/{project_id}/availability/check?start_date={start_date}&end_date={end_date}")

class BacklogServiceClient(ServiceClient):
    def __init__(self):
        super().__init__(
            base_url=os.environ.get("BACKLOG_SERVICE_URL", "http://backlog-service.dsm.svc.cluster.local"),
            service_name="Backlog Service"
        )

    async def get_backlog_tasks(self, project_id: str) -> List[Dict[str, Any]]:
        async with backlog_service_circuit_breaker.context():
            return await self._make_request("GET", f"/backlogs/{project_id}")

    async def get_backlog_summary(self, project_id: str) -> Dict[str, Any]:
        async with backlog_service_circuit_breaker.context():
            return await self._make_request("GET", f"/backlogs/{project_id}/summary")

    async def update_task_assignment(self, task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with backlog_service_circuit_breaker.context():
            return await self._make_request("PUT", f"/tasks/{task_id}", json=payload)

class SprintServiceClient(ServiceClient):
    def __init__(self):
        super().__init__(
            base_url=os.environ.get("SPRINT_SERVICE_URL", "http://sprint-service.dsm.svc.cluster.local"),
            service_name="Sprint Service"
        )

    async def get_sprints_by_project(self, project_id: str) -> List[Dict[str, Any]]:
        async with sprint_service_circuit_breaker.context():
            return await self._make_request("GET", f"/sprints/by-project/{project_id}")

    async def get_active_sprints(self) -> List[Dict[str, Any]]:
        async with sprint_service_circuit_breaker.context():
            return await self._make_request("GET", "/sprints/active")

    async def create_sprint(self, project_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        logger.debug("SprintServiceClient: Sending payload to Sprint Service", project_id=project_id, payload=payload)
        async with sprint_service_circuit_breaker.context():
            return await self._make_request("POST", f"/sprints/{project_id}", json=payload)

    async def get_sprint_task_summary(self, sprint_id: str) -> Dict[str, Any]:
        async with sprint_service_circuit_breaker.context():
            return await self._make_request("GET", f"/sprints/{sprint_id}/task-summary")

    async def close_sprint(self, sprint_id: str) -> Dict[str, Any]:
        logger.debug("SprintServiceClient: Sending close sprint request to Sprint Service", sprint_id=sprint_id)
        async with sprint_service_circuit_breaker.context():
            return await self._make_request("POST", f"/sprints/{sprint_id}/close")

class ChronicleServiceClient(ServiceClient):
    def __init__(self):
        super().__init__(
            base_url=os.environ.get("CHRONICLE_SERVICE_URL", "http://chronicle-service.dsm.svc.cluster.local"),
            service_name="Chronicle Service"
        )

    async def record_daily_scrum_report(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with chronicle_service_circuit_breaker.context():
            return await self._make_request("POST", "/v1/notes/daily_scrum_report", json=payload)

    async def record_decision_audit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with chronicle_service_circuit_breaker.context():
            return await self._make_request("POST", "/v1/notes/decision_audit", json=payload)

    async def record_sprint_retrospective(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with chronicle_service_circuit_breaker.context():
            return await self._make_request("POST", "/v1/notes/sprint_retrospective", json=payload)