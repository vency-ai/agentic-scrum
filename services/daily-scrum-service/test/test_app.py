import pytest
import requests_mock
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import os
import requests # Import requests to access its exceptions
import random

# Set environment variable for testing
os.environ["SPRINT_SERVICE_URL"] = "http://mock-sprint-service"
os.environ["CHRONICLE_SERVICE_URL"] = "http://mock-chronicle-service"

import app as daily_scrum_app

client = TestClient(daily_scrum_app.app)

@pytest.fixture(autouse=True)
def mock_env_vars():
    with patch.dict(os.environ, {
        "SPRINT_SERVICE_URL": "http://mock-sprint-service",
        "CHRONICLE_SERVICE_URL": "http://mock-chronicle-service"
    }):
        yield

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_run_daily_scrum_no_tasks():
    with requests_mock.Mocker() as m:
        m.get("http://mock-sprint-service/sprints/SPR001", json={"sprint_id": "SPR001", "tasks": []})
        m.get("http://mock-sprint-service/sprints/SPR001/summary", json={
            "sprint_id": "SPR001",
            "overall_progress_percentage": 0,
            "total_tasks": 0,
            "task_breakdown": {
                "completed_count": 0,
                "in_progress_count": 0,
                "not_started_count": 0,
                "blocked_count": 0
            }
        })
        chronicle_post_mock = m.post("http://mock-chronicle-service/v1/notes/daily_scrum_report", json={"message": "Note recorded"}, status_code=201)

        response = client.post("/scrums/SPR001/run")
        assert response.status_code == 200
        assert response.json() == daily_scrum_app.SimulationResult(
            message="No tasks found for sprint.",
            tasks_updated_count=0,
            updates=[],
            sprint_summary=None
        ).model_dump()
        
        # Assert that Sprint Service was called for tasks and summary
        assert m.called
        assert m.call_count == 2 # One GET for sprint, one GET for summary
        # Assert that Chronicle Service was NOT called
        assert not chronicle_post_mock.called 

def test_run_daily_scrum_with_tasks_and_summary():
    with requests_mock.Mocker() as m:
        # Mock initial sprint tasks
        m.get("http://mock-sprint-service/sprints/SPR001", json={
            "sprint_id": "SPR001",
            "tasks": [
                {"task_id": "TASK001", "status": "not_started", "progress_percentage": 0},
                {"task_id": "TASK002", "status": "in_progress", "progress_percentage": 50},
                {"task_id": "TASK003", "status": "completed", "progress_percentage": 100}
            ]
        })
        
        # Mock task progress updates (randomly some tasks will be updated)
        # We'll mock a generic POST for any task progress URL
        m.post(requests_mock.ANY, json={"message": "Task updated"}, status_code=200)

        # Mock final sprint summary after updates
        m.get("http://mock-sprint-service/sprints/SPR001/summary", json={
            "sprint_id": "SPR001",
            "overall_progress_percentage": 75,
            "total_tasks": 3,
            "task_breakdown": {
                "completed_count": 2,
                "in_progress_count": 1,
                "not_started_count": 0,
                "blocked_count": 0
            }
        })
        chronicle_post_mock = m.post("http://mock-chronicle-service/v1/notes/daily_scrum_report", json={"message": "Note recorded"}, status_code=201)

        response = client.post("/scrums/SPR001/run")
        assert response.status_code == 200
        response_data = response.json()
        
        assert response_data["message"] == "Daily scrum simulation completed for sprint SPR001"
        assert response_data["tasks_updated_count"] >= 0 # Can be 0 if random.choice is always False
        assert "updates" in response_data
        assert "sprint_summary" in response_data
        assert response_data["sprint_summary"]["sprint_id"] == "SPR001"
        assert response_data["sprint_summary"]["overall_progress_percentage"] == 75
        assert response_data["sprint_summary"]["total_tasks"] == 3
        assert response_data["sprint_summary"]["task_breakdown"]["completed_count"] == 2
        
        # Assert that Chronicle Service was called
        assert chronicle_post_mock.called_once 
        # Total calls: 1 GET sprint, 1 GET summary, 0-3 POST task updates, 1 POST chronicle
        assert m.call_count >= 3 

def test_run_daily_scrum_atomic_simulation():
    with requests_mock.Mocker() as m:
        # Mock initial sprint tasks for F-AUTO-01
        m.get("http://mock-sprint-service/sprints/SPR002", json={
            "sprint_id": "SPR002",
            "tasks": [
                {"task_id": "TASK004", "status": "not_started", "progress_percentage": 0},
                {"task_id": "TASK005", "status": "in_progress", "progress_percentage": 20},
                {"task_id": "TASK006", "status": "not_started", "progress_percentage": 0}
            ]
        })
        
        # Mock task progress updates
        m.post("http://mock-sprint-service/tasks/TASK004/progress", json={"message": "Task updated"}, status_code=200)
        m.post("http://mock-sprint-service/tasks/TASK005/progress", json={"message": "Task updated"}, status_code=200)
        m.post("http://mock-sprint-service/tasks/TASK006/progress", json={"message": "Task updated"}, status_code=200)

        # Mock sprint summary for F-AUTO-02 (even though this test focuses on F-AUTO-01, the app will call it)
        m.get("http://mock-sprint-service/sprints/SPR002/summary", json={
            "sprint_id": "SPR002",
            "overall_progress_percentage": 50,
            "total_tasks": 3,
            "task_breakdown": {
                "completed_count": 1,
                "in_progress_count": 2,
                "not_started_count": 0,
                "blocked_count": 0
            }
        })
        chronicle_post_mock = m.post("http://mock-chronicle-service/v1/notes/daily_scrum_report", json={"message": "Note recorded"}, status_code=201)


        # Patch random.choice to ensure at least one task is updated for predictable testing
        with patch('random.choice', return_value=True):
            response = client.post("/scrums/SPR002/run")
            assert response.status_code == 200
            response_data = response.json()
            
            assert response_data["message"] == "Daily scrum simulation completed for sprint SPR002"
            assert response_data["tasks_updated_count"] > 0 # At least one task should be updated
            assert len(response_data["updates"]) > 0
            assert "sprint_summary" in response_data # F-AUTO-02 part should still be present
        
        assert chronicle_post_mock.called_once # Chronicle service should be called
        assert m.call_count == 5 # GET sprint, GET summary, 3 POST task updates, POST chronicle

def test_run_daily_scrum_reports_to_chronicle():
    with requests_mock.Mocker() as m:
        # Mock Sprint Service calls
        m.get("http://mock-sprint-service/sprints/SPR003", json={
            "sprint_id": "SPR003",
            "tasks": [{"task_id": "TASK007", "status": "not_started", "progress_percentage": 0}]
        })
        m.post("http://mock-sprint-service/tasks/TASK007/progress", json={"message": "Task updated"}, status_code=200)
        m.get("http://mock-sprint-service/sprints/SPR003/summary", json={
            "sprint_id": "SPR003",
            "overall_progress_percentage": 50,
            "total_tasks": 1,
            "task_breakdown": {"completed_count": 0, "in_progress_count": 1, "not_started_count": 0, "blocked_count": 0}
        })

        # Mock Chronicle Service call and capture the request
        chronicle_mock = m.post("http://mock-chronicle-service/v1/notes/daily_scrum_report", json={"message": "Note recorded"}, status_code=201)

        with patch('random.choice', return_value=True): # Ensure task is updated
            response = client.post("/scrums/SPR003/run")
            assert response.status_code == 200
            
            # Assert that Chronicle Service was called
            assert chronicle_mock.called_once
            assert chronicle_mock.last_request.json()["sprint_id"] == "SPR003"
            assert "Daily scrum for sprint SPR003 completed." in chronicle_mock.last_request.json()["summary"]
            assert "task_updates" in chronicle_mock.last_request.json()
            assert "sprint_summary_data" in chronicle_mock.last_request.json()

def test_run_daily_scrum_chronicle_service_unavailable():
    with requests_mock.Mocker() as m:
        # Mock Sprint Service calls (successful)
        m.get("http://mock-sprint-service/sprints/SPR004", json={
            "sprint_id": "SPR004",
            "tasks": [{"task_id": "TASK008", "status": "not_started", "progress_percentage": 0}]
        })
        m.post("http://mock-sprint-service/tasks/TASK008/progress", json={"message": "Task updated"}, status_code=200)
        m.get("http://mock-sprint-service/sprints/SPR004/summary", json={
            "sprint_id": "SPR004",
            "overall_progress_percentage": 50,
            "total_tasks": 1,
            "task_breakdown": {"completed_count": 0, "in_progress_count": 1, "not_started_count": 0, "blocked_count": 0}
        })

        # Mock Chronicle Service failure
        chronicle_mock = m.post("http://mock-chronicle-service/v1/notes/daily_scrum_report", exc=requests.exceptions.RequestException)

        with patch('random.choice', return_value=True): # Ensure task is updated
            response = client.post("/scrums/SPR004/run")
            assert response.status_code == 200 # Should still succeed as reporting is a side effect
            response_data = response.json()
            assert response_data["message"] == "Daily scrum simulation completed for sprint SPR004"
            # Check that the Chronicle Service was attempted to be called
            assert chronicle_mock.called # Assert that the mock was called
            # Check that the response does not contain Chronicle-specific error, as it's logged internally
            assert "sprint_summary" in response_data # Ensure other parts of the response are still present

def test_run_daily_scrum_sprint_not_found():
    with requests_mock.Mocker() as m:
        m.get("http://mock-sprint-service/sprints/NONEXISTENT", status_code=404)
        response = client.post("/scrums/NONEXISTENT/run")
        assert response.status_code == 404
        assert response.json() == {"detail": "Sprint NONEXISTENT not found."}

def test_run_daily_scrum_sprint_service_unavailable():
    with requests_mock.Mocker() as m:
        m.get("http://mock-sprint-service/sprints/SPR001", exc=requests.exceptions.RequestException) # Corrected
        response = client.post("/scrums/SPR001/run")
        assert response.status_code == 500
        assert response.json() == {"detail": "Failed to connect to Sprint Service."}

def test_run_daily_scrum_sprint_summary_unavailable():
    with requests_mock.Mocker() as m:
        # Mock initial sprint tasks
        m.get("http://mock-sprint-service/sprints/SPR001", json={
            "sprint_id": "SPR001",
            "tasks": [
                {"task_id": "TASK001", "status": "not_started", "progress_percentage": 0}
            ]
        })
        m.post(requests_mock.ANY, json={"message": "Task updated"}, status_code=200)
        # Mock sprint summary failure
        m.get("http://mock-sprint-service/sprints/SPR001/summary", exc=requests.exceptions.RequestException) # Corrected

        response = client.post("/scrums/SPR001/run")
        assert response.status_code == 200 # Still 200 because task updates might have succeeded
        response_data = response.json()
        assert response_data["message"] == "Daily scrum simulation completed for sprint SPR001"
        assert "sprint_summary" in response_data
        assert response_data["sprint_summary"] is None