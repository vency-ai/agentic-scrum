import structlog
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from typing import Dict, Any, Optional, List
import asyncio
import concurrent.futures

logger = structlog.get_logger()

class KubernetesClient:
    def __init__(self):
        self.api_client = self._load_k8s_config()
        self.batch_v1_api = client.BatchV1Api(self.api_client)
        self.core_v1_api = client.CoreV1Api(self.api_client)
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

    def _load_k8s_config(self):
        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config.")
        except config.ConfigException:
            try:
                config.load_kube_config()
                logger.info("Loaded kubeconfig for local development.")
            except config.ConfigException:
                logger.error("Could not configure Kubernetes client", reason="Neither in-cluster nor kubeconfig found.")
                raise RuntimeError("Kubernetes configuration not found.")
        return client.ApiClient()

    async def create_cronjob(self, namespace: str, cronjob_manifest: Dict[str, Any]) -> Dict[str, Any]:
        logger.info("Creating CronJob", namespace=namespace, cronjob_name=cronjob_manifest.get("metadata", {}).get("name"))
        logger.debug("Manifest to be sent to Kubernetes API", manifest=cronjob_manifest)
        try:
            loop = asyncio.get_event_loop()
            
            def _create_blocking():
                try:
                    return self.batch_v1_api.create_namespaced_cron_job(
                        namespace=namespace,
                        body=cronjob_manifest
                    )
                except ApiException as e:
                    logger.error("ApiException inside executor during CronJob creation", 
                                 status=e.status, reason=e.reason, body=e.body, exc_info=True)
                    raise # Re-raise to be caught by the outer try-except
                except Exception as e:
                    logger.error("Unexpected Exception inside executor during CronJob creation", 
                                 error=str(e), exc_info=True)
                    raise # Re-raise to be caught by the outer try-except

            api_response = await loop.run_in_executor(
                self.executor,
                _create_blocking
            )
            
            logger.debug("Raw API response from create_namespaced_cron_job", raw_api_response=api_response)

            if not isinstance(api_response, client.V1CronJob):
                logger.error("Unexpected API response type for CronJob creation", 
                             expected_type="V1CronJob", actual_type=type(api_response),
                             api_response=str(api_response))
                # Depending on severity, could raise an exception here or return an error status
                raise RuntimeError(f"Unexpected API response type: {type(api_response)}")

            cj_name = cronjob_manifest.get("metadata", {}).get("name", "unknown-cronjob")
            logger.info("Successfully created CronJob", namespace=namespace, cronjob_name=cj_name, api_response=api_response.to_dict())
            return api_response.to_dict()
        except ApiException as e:
            logger.error("Error creating CronJob (ApiException caught outside executor)", 
                         status=e.status, reason=e.reason, body=e.body, exc_info=True)
            raise
        except Exception as e: # Catch any other unexpected exceptions
            logger.error("Error creating CronJob (Unexpected Exception caught outside executor)", 
                         error=str(e), exc_info=True)
            raise

    async def get_cronjob(self, namespace: str, name: str) -> Optional[Dict[str, Any]]:
        logger.info("Getting CronJob", namespace=namespace, cronjob_name=name)
        try:
            loop = asyncio.get_event_loop()
            api_response = await loop.run_in_executor(
                self.executor,
                lambda: self.batch_v1_api.read_namespaced_cron_job(
                    name=name,
                    namespace=namespace
                )
            )
            return api_response.to_dict()
        except ApiException as e:
            if e.status == 404:
                logger.info("CronJob not found", namespace=namespace, cronjob_name=name)
                return None
            logger.error("Error getting CronJob", status=e.status, reason=e.reason, body=e.body)
            raise

    async def check_cronjob_exists(self, namespace: str, name: str) -> bool:
        """Checks if a CronJob with the given name exists in the namespace."""
        logger.info("Checking if CronJob exists", namespace=namespace, cronjob_name=name)
        cronjob = await self.get_cronjob(namespace=namespace, name=name)
        return cronjob is not None

    async def delete_cronjob(self, namespace: str, name: str) -> Dict[str, Any]:
        logger.info("Deleting CronJob", namespace=namespace, cronjob_name=name)
        try:
            loop = asyncio.get_event_loop()
            api_response = await loop.run_in_executor(
                self.executor,
                lambda: self.batch_v1_api.delete_namespaced_cron_job(
                    name=name,
                    namespace=namespace,
                    body=client.V1DeleteOptions()
                )
            )
            return api_response.to_dict()
        except ApiException as e:
            if e.status == 404:
                logger.info("CronJob not found for deletion", namespace=namespace, cronjob_name=name)
                return {"message": f"CronJob {name} not found."}
            logger.error("Error deleting CronJob", status=e.status, reason=e.reason, body=e.body)
            raise

    async def list_cronjobs(self, namespace: str, label_selector: Optional[str] = None) -> List[Dict[str, Any]]:
        logger.info("Listing CronJobs", namespace=namespace, label_selector=label_selector)
        try:
            loop = asyncio.get_event_loop()
            if label_selector:
                api_response = await loop.run_in_executor(
                    self.executor,
                    lambda: self.batch_v1_api.list_namespaced_cron_job(namespace=namespace, label_selector=label_selector)
                )
            else:
                api_response = await loop.run_in_executor(
                    self.executor,
                    lambda: self.batch_v1_api.list_namespaced_cron_job(namespace=namespace)
                )
            return [item.to_dict() for item in api_response.items]
        except ApiException as e:
            logger.error("Error listing CronJobs", status=e.status, reason=e.reason, body=e.body)
            raise