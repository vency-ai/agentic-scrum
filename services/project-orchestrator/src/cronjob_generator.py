import os
import structlog
from jinja2 import Environment, FileSystemLoader
from typing import Dict, Any, Optional, List
from k8s_client import KubernetesClient
import yaml # Added missing import

logger = structlog.get_logger()

class CronJobGenerator:
    def __init__(self):
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.jinja_env = Environment(loader=FileSystemLoader(template_dir))
        self.k8s_client = KubernetesClient()
        self.namespace = os.environ.get("K8S_NAMESPACE", "dsm")

    def _generate_cronjob_manifest(self, data: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Generating CronJob manifest from template", data=data)
        template = self.jinja_env.get_template("cronjob_template.yaml")
        rendered_manifest = template.render(data)
        return yaml.safe_load(rendered_manifest)

    async def deploy_cronjob(self, project_id: str, sprint_id: str, schedule: str) -> Dict[str, Any]:
        cronjob_name = f"run-dailyscrum-{project_id.lower()}-{sprint_id.lower()}"
        logger.info("Deploying CronJob", cronjob_name=cronjob_name, project_id=project_id, sprint_id=sprint_id, schedule=schedule)

        manifest_data = {
            "cronjob_name": cronjob_name,
            "project_id": project_id,
            "sprint_id": sprint_id,
            "schedule": schedule
        }
        cronjob_manifest = self._generate_cronjob_manifest(manifest_data)
        
        logger.debug("Generated CronJob manifest", cronjob_manifest=cronjob_manifest) # Added debug log

        # Ensure the manifest is valid before deploying
        if not cronjob_manifest:
            logger.error("Generated CronJob manifest is empty or invalid. Raising ValueError.", exc_info=True)
            raise ValueError("Invalid CronJob manifest generated.")
        
        logger.debug("Attempting to deploy CronJob with manifest:", manifest=yaml.dump(cronjob_manifest, default_flow_style=False)) # Added this line to log the full manifest

        try:
            logger.debug("Calling k8s_client.create_cronjob", namespace=self.namespace, cronjob_manifest_name=cronjob_manifest.get("metadata", {}).get("name"))
            response = await self.k8s_client.create_cronjob(self.namespace, cronjob_manifest)
            logger.info("CronJob deployed successfully", cronjob_name=cronjob_name, response=response)
            return {"cronjob_name": cronjob_name, "status": "deployed", "response": response}
        except Exception as e:
            logger.error("Failed to deploy CronJob in cronjob_generator", cronjob_name=cronjob_name, error=str(e), exc_info=True)
            raise

    async def delete_cronjob(self, cronjob_name: str) -> Dict[str, Any]:
        logger.info("Deleting CronJob", cronjob_name=cronjob_name)
        try:
            response = await self.k8s_client.delete_cronjob(self.namespace, cronjob_name)
            logger.info("CronJob deleted successfully", cronjob_name=cronjob_name, response=response)
            return {"cronjob_name": cronjob_name, "status": "deleted", "response": response}
        except Exception as e:
            logger.error("Failed to delete CronJob", cronjob_name=cronjob_name, error=str(e))
            raise

    async def get_cronjob_status(self, cronjob_name: str) -> Optional[Dict[str, Any]]:
        logger.info("Getting CronJob status", cronjob_name=cronjob_name)
        try:
            cronjob = await self.k8s_client.get_cronjob(self.namespace, cronjob_name)
            if cronjob:
                return {
                    "name": cronjob.get("metadata", {}).get("name"),
                    "schedule": cronjob.get("spec", {}).get("schedule"),
                    "status": "active" if cronjob.get("spec", {}).get("suspend") is not True else "suspended",
                    "last_schedule_time": cronjob.get("status", {}).get("lastScheduleTime"),
                }
            return None
        except Exception as e:
            logger.error("Failed to get CronJob status", cronjob_name=cronjob_name, error=str(e))
            raise

    async def list_project_cronjobs(self, project_id: str) -> List[Dict[str, Any]]:
        label_selector = f"project={project_id}"
        logger.info("Listing CronJobs for project", project_id=project_id, label_selector=label_selector)
        try:
            cronjobs = await self.k8s_client.list_cronjobs(self.namespace, label_selector=label_selector)
            return [
                {
                    "name": cj.get("metadata", {}).get("name"),
                    "schedule": cj.get("spec", {}).get("schedule"),
                    "status": "active" if cj.get("spec", {}).get("suspend") is not True else "suspended",
                    "last_schedule_time": cj.get("status", {}).get("lastScheduleTime"),
                }
                for cj in cronjobs
            ]
        except Exception as e:
            logger.error("Failed to list CronJobs for project", project_id=project_id, error=str(e))
            raise