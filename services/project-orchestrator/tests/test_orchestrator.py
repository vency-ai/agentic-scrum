import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import os
import json
import datetime

# Adjust path to import modules from src
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from service_clients import ProjectServiceClient, BacklogServiceClient, SprintServiceClient, ChronicleServiceClient
from project_analyzer import ProjectAnalyzer
from decision_engine import DecisionEngine
from k8s_client import KubernetesClient
from cronjob_generator import CronJobGenerator

class TestServiceClients(unittest.IsolatedAsyncioTestCase):

    @patch('httpx.AsyncClient')
    async def test_project_service_client(self, MockAsyncClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"project_id": "TEST-001", "name": "Test Project"}
        mock_response.raise_for_status.return_value = None
        MockAsyncClient.return_value.request = AsyncMock(return_value=mock_response)

        client = ProjectServiceClient()
        result = await client.get_project("TEST-001")
        self.assertEqual(result, {"project_id": "TEST-001", "name": "Test Project"})
        MockAsyncClient.return_value.request.assert_called_once_with(
            "GET", "http://project-service.dsm.svc.cluster.local/projects/TEST-001"
        )

    @patch('httpx.AsyncClient')
    async def test_backlog_service_client_summary(self, MockAsyncClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"total_tasks": 10, "unassigned_tasks": 5}
        mock_response.raise_for_status.return_value = None
        MockAsyncClient.return_value.request = AsyncMock(return_value=mock_response)

        client = BacklogServiceClient()
        result = await client.get_backlog_summary("TEST-001")
        self.assertEqual(result, {"total_tasks": 10, "unassigned_tasks": 5})
        MockAsyncClient.return_value.request.assert_called_once_with(
            "GET", "http://backlog-service.dsm.svc.cluster.local/backlogs/TEST-001/summary"
        )

    @patch('httpx.AsyncClient')
    async def test_sprint_service_client_active_sprints(self, MockAsyncClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            "sprint_id": "TEST-001-S01", "project_id": "TEST-001", "status": "active"
        }]
        mock_response.raise_for_status.return_value = None
        MockAsyncClient.return_value.request = AsyncMock(return_value=mock_response)

        client = SprintServiceClient()
        result = await client.get_active_sprints()
        self.assertEqual(result[0]["sprint_id"], "TEST-001-S01")

    @patch('httpx.AsyncClient')
    async def test_chronicle_service_client(self, MockAsyncClient):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"message": "Report recorded"}
        mock_response.raise_for_status.return_value = None
        MockAsyncClient.return_value.request = AsyncMock(return_value=mock_response)

        client = ChronicleServiceClient()
        payload = {"event_type": "TEST_EVENT"}
        result = await client.record_daily_scrum_report(payload)
        self.assertEqual(result, {"message": "Report recorded"})

class TestProjectAnalyzer(unittest.IsolatedAsyncioTestCase):

    @patch('project_analyzer.ProjectServiceClient') # Changed patch target
    @patch('project_analyzer.BacklogServiceClient') 
    @patch('project_analyzer.SprintServiceClient') 
    async def test_analyze_project_state(self, MockSprintClient, MockBacklogClient, MockProjectClient):
        MockProjectClient.return_value.get_project = AsyncMock(return_value={"project_id": "TEST-001", "name": "Test Project"})
        MockProjectClient.return_value.get_team_members = AsyncMock(return_value=[{"id": "1"}, {"id": "2"}])
        
        today = datetime.date.today()
        two_weeks_later = today + datetime.timedelta(days=14)
        # Explicitly make check_team_availability an AsyncMock and set its return_value
        MockProjectClient.return_value.check_team_availability = AsyncMock(return_value={"status": "available"})
        
        # Explicitly make get_backlog_summary an AsyncMock and set its return_value
                # Explicitly make get_backlog_summary an AsyncMock and set its return_value
        MockBacklogClient.return_value.get_backlog_summary = AsyncMock(return_value={"total_tasks": 15, "unassigned_for_sprint_count": 8})
        
        # Explicitly make get_active_sprints an AsyncMock and set its return_value
        MockSprintClient.return_value.get_active_sprints = AsyncMock(return_value=[])
        MockSprintClient.return_value.get_sprints_by_project = AsyncMock(return_value=[])

        analyzer = ProjectAnalyzer()
        result = await analyzer.analyze_project_state("TEST-001", sprint_duration_weeks=2)

        self.assertEqual(result["project_id"], "TEST-001")
        self.assertEqual(result["team_size"], 2)
        self.assertEqual(result["backlog_tasks"], 15) # Added assertion
        self.assertEqual(result["unassigned_tasks"], 8)
        self.assertFalse(result["has_active_sprint_for_project"])
        MockProjectClient.return_value.check_team_availability.assert_called_once_with("TEST-001", str(today), str(two_weeks_later))

class TestDecisionEngine(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_k8s_client = MagicMock(spec=KubernetesClient)

    async def test_make_orchestration_decisions_create_sprint(self):
        project_analysis = {
            "project_id": "TEST-001",
            "unassigned_tasks": 10,
            "has_active_sprint_for_project": False,
            "team_size": 3,
            "team_availability": {"status": "available", "conflicts": []},
            "sprint_count": 0
        }
        options = {
            "create_sprint_if_needed": True,
            "assign_tasks": True,
            "create_cronjob": True,
            "max_tasks_per_sprint": 5
        }

        engine = DecisionEngine(self.mock_k8s_client)
        decisions = await engine.make_orchestration_decisions(project_analysis, options)

        self.assertTrue(decisions["create_new_sprint"])
        self.assertEqual(decisions["tasks_to_assign"], 5)
        self.assertTrue(decisions["cronjob_created"])
        self.assertEqual(decisions["sprint_name"], "TEST-001-S01")

    async def test_make_orchestration_decisions_no_sprint_needed_due_to_active_sprint(self):
        self.mock_k8s_client.check_cronjob_exists = AsyncMock(return_value=True)
        project_analysis = {
            "project_id": "TEST-001",
            "unassigned_tasks": 5,
            "has_active_sprint_for_project": True,
            "current_active_sprint": {"sprint_id": "TEST-001-S01"},
            "team_size": 3,
            "team_availability": {"status": "available", "conflicts": []}
        }
        options = {}

        engine = DecisionEngine(self.mock_k8s_client)
        decisions = await engine.make_orchestration_decisions(project_analysis, options)

        self.assertFalse(decisions["create_new_sprint"])
        self.assertFalse(decisions["cronjob_created"])
        self.assertIn("Active sprint TEST-001-S01 found with an existing CronJob", decisions["reasoning"])
        self.mock_k8s_client.check_cronjob_exists.assert_called_once_with(namespace="dsm", name="run-dailyscrum-test-001-test-001-s01")

    async def test_make_orchestration_decisions_self_heal_missing_cronjob(self):
        self.mock_k8s_client.check_cronjob_exists = AsyncMock(return_value=False)
        project_analysis = {
            "project_id": "TEST-001",
            "unassigned_tasks": 5,
            "has_active_sprint_for_project": True,
            "current_active_sprint": {"sprint_id": "TEST-001-S01"},
            "team_size": 3,
            "team_availability": {"status": "available", "conflicts": []}
        }
        options = {}

        engine = DecisionEngine(self.mock_k8s_client)
        decisions = await engine.make_orchestration_decisions(project_analysis, options)

        self.assertFalse(decisions["create_new_sprint"])
        self.assertTrue(decisions["cronjob_created"])
        self.assertEqual(decisions["sprint_name"], "TEST-001-S01")
        self.assertIn("corresponding CronJob was missing. Recreating", decisions["reasoning"])
        self.mock_k8s_client.check_cronjob_exists.assert_called_once_with(namespace="dsm", name="run-dailyscrum-test-001-test-001-s01")

    async def test_make_orchestration_decisions_no_sprint_needed(self):
        project_analysis = {
            "project_id": "TEST-001",
            "unassigned_tasks": 0,
            "has_active_sprint_for_project": False,
            "team_size": 3,
            "team_availability": {"status": "available", "conflicts": []}
        }
        options = {
            "create_sprint_if_needed": True,
            "assign_tasks": True,
            "create_cronjob": True,
            "max_tasks_per_sprint": 5
        }

        engine = DecisionEngine(self.mock_k8s_client)
        decisions = await engine.make_orchestration_decisions(project_analysis, options)

        self.assertFalse(decisions["create_new_sprint"])
        self.assertEqual(decisions["tasks_to_assign"], 0)
        self.assertFalse(decisions["cronjob_created"])

class TestKubernetesClient(unittest.IsolatedAsyncioTestCase):

    @patch('kubernetes.config.load_incluster_config')
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.BatchV1Api')
    @patch('kubernetes.client.CoreV1Api')
    async def test_create_cronjob(self, MockCoreV1Api, MockBatchV1Api, mock_load_kube_config, mock_load_incluster_config):

        mock_load_incluster_config.return_value = None # Allow fallback to load_kube_config
        mock_load_kube_config.return_value = None # Mock successful loading of kube_config
        
        mock_batch_api_instance = MagicMock()
        mock_create_cronjob_method = AsyncMock()
        mock_create_cronjob_method.return_value = MagicMock(to_dict=MagicMock(return_value={"metadata": {"name": "test-cronjob"}}))
        mock_batch_api_instance.create_namespaced_cron_job = mock_create_cronjob_method
        MockBatchV1Api.return_value = mock_batch_api_instance

        client = KubernetesClient()
        manifest = {"apiVersion": "batch/v1", "kind": "CronJob", "metadata": {"name": "test-cronjob"}}
        result = await client.create_cronjob("dsm", manifest)
        self.assertEqual(result, {"metadata": {"name": "test-cronjob"}})
        mock_batch_api_instance.create_namespaced_cron_job.assert_called_once()

    mock_batch_api_instance.create_namespaced_cron_job.assert_called_once()

    @patch('kubernetes.config.load_incluster_config')
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.BatchV1Api')
    @patch('kubernetes.client.CoreV1Api')
    async def test_create_cronjob_api_exception(self, MockCoreV1Api, MockBatchV1Api, mock_load_kube_config, mock_load_incluster_config):
        mock_load_incluster_config.return_value = None
        mock_load_kube_config.return_value = None

        mock_batch_api_instance = MagicMock()
        mock_create_cronjob_method = AsyncMock(side_effect=client.rest.ApiException(status=400, reason="Bad Request"))
        mock_batch_api_instance.create_namespaced_cron_job = mock_create_cronjob_method
        MockBatchV1Api.return_value = mock_batch_api_instance

        k8s_client_instance = KubernetesClient()
        manifest = {"apiVersion": "batch/v1", "kind": "CronJob", "metadata": {"name": "test-cronjob"}}
        
        with self.assertRaises(client.rest.ApiException) as cm:
            await k8s_client_instance.create_cronjob("dsm", manifest)
        self.assertEqual(cm.exception.status, 400)
        mock_batch_api_instance.create_namespaced_cron_job.assert_called_once()

    @patch('kubernetes.config.load_incluster_config')
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.BatchV1Api')
    @patch('kubernetes.client.CoreV1Api')
    async def test_create_cronjob_generic_exception(self, MockCoreV1Api, MockBatchV1Api, mock_load_kube_config, mock_load_incluster_config):
        mock_load_incluster_config.return_value = None
        mock_load_kube_config.return_value = None

        mock_batch_api_instance = MagicMock()
        mock_create_cronjob_method = AsyncMock(side_effect=Exception("Connection error"))
        mock_batch_api_instance.create_namespaced_cron_job = mock_create_cronjob_method
        MockBatchV1Api.return_value = mock_batch_api_instance

        k8s_client_instance = KubernetesClient()
        manifest = {"apiVersion": "batch/v1", "kind": "CronJob", "metadata": {"name": "test-cronjob"}}
        
        with self.assertRaises(Exception) as cm:
            await k8s_client_instance.create_cronjob("dsm", manifest)
        self.assertIn("Connection error", str(cm.exception))
        mock_batch_api_instance.create_namespaced_cron_job.assert_called_once()

    @patch('kubernetes.config.load_incluster_config')
    @patch('kubernetes.config.load_kube_config')
    @patch('kubernetes.client.BatchV1Api')
    @patch('kubernetes.client.CoreV1Api')
    async def test_delete_cronjob(self, MockCoreV1Api, MockBatchV1Api, mock_load_kube_config, mock_load_incluster_config):

        mock_load_incluster_config.return_value = None # Allow fallback to load_kube_config
        mock_load_kube_config.return_value = None # Mock successful loading of kube_config
        
        mock_batch_api_instance = MagicMock()
        mock_delete_cronjob_method = AsyncMock()
        mock_delete_cronjob_method.return_value = MagicMock(to_dict=MagicMock(return_value={"status": "Success"}))
        mock_batch_api_instance.delete_namespaced_cron_job = mock_delete_cronjob_method
        MockBatchV1Api.return_value = mock_batch_api_instance

        client = KubernetesClient()
        result = await client.delete_cronjob("dsm", "test-cronjob")
        self.assertEqual(result, {"status": "Success"})
        mock_batch_api_instance.delete_namespaced_cron_job.assert_called_once()

class TestCronJobGenerator(unittest.IsolatedAsyncioTestCase):

    @patch('cronjob_generator.KubernetesClient')
    @patch('jinja2.FileSystemLoader')
    @patch('jinja2.Environment')
    @patch('yaml.safe_load')
    async def test_deploy_cronjob(self, mock_safe_load, MockEnvironment, MockFileSystemLoader, MockKubernetesClient):
        mock_template = MagicMock()
        mock_template.render.return_value = "---\napiVersion: batch/v1\nkind: CronJob\nmetadata:\n  name: test-cronjob\n"
        MockEnvironment.return_value.get_template.return_value = mock_template
        mock_safe_load.return_value = {"metadata": {"name": "test-cronjob"}}

        mock_k8s_client_instance = AsyncMock()
        mock_k8s_client_instance.create_cronjob.return_value = {"metadata": {"name": "test-cronjob"}}
        MockKubernetesClient.return_value = mock_k8s_client_instance

        generator = CronJobGenerator()
        result = await generator.deploy_cronjob("TEST-001", "S01", "* * * * *")

        self.assertEqual(result["cronjob_name"], "run-dailyscrum-test-001-s01")
        self.assertEqual(result["status"], "deployed")
        mock_k8s_client_instance.create_cronjob.assert_called_once()

    @patch('cronjob_generator.KubernetesClient')
    async def test_delete_cronjob_generator(self, MockKubernetesClient):
        mock_k8s_client_instance = AsyncMock()
        mock_k8s_client_instance.delete_cronjob.return_value = {"status": "Success"}
        MockKubernetesClient.return_value = mock_k8s_client_instance

        generator = CronJobGenerator()
        result = await generator.delete_cronjob("test-cronjob")

        self.assertEqual(result["cronjob_name"], "test-cronjob")
        self.assertEqual(result["status"], "deleted")
        mock_k8s_client_instance.delete_cronjob.assert_called_once_with("dsm", "test-cronjob")

    @patch('cronjob_generator.KubernetesClient')
    @patch('jinja2.FileSystemLoader')
    @patch('jinja2.Environment')
    @patch('yaml.safe_load')
    async def test_deploy_cronjob_failure(self, mock_safe_load, MockEnvironment, MockFileSystemLoader, MockKubernetesClient):
        mock_template = MagicMock()
        mock_template.render.return_value = "---\napiVersion: batch/v1\nkind: CronJob\nmetadata:\n  name: test-cronjob\n"
        MockEnvironment.return_value.get_template.return_value = mock_template
        mock_safe_load.return_value = {"metadata": {"name": "test-cronjob"}}

        mock_k8s_client_instance = AsyncMock()
        mock_k8s_client_instance.create_cronjob.side_effect = Exception("K8s API error")
        MockKubernetesClient.return_value = mock_k8s_client_instance

        generator = CronJobGenerator()
        with self.assertRaises(Exception) as cm:
            await generator.deploy_cronjob("TEST-001", "S01", "* * * * *")
        self.assertIn("K8s API error", str(cm.exception))
        mock_k8s_client_instance.create_cronjob.assert_called_once()

if __name__ == '__main__':
    unittest.main()
