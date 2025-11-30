import asyncio
import json
import os
import uuid
from urllib.parse import urlparse

import redis.asyncio as redis
import structlog
import psycopg2

from utils import get_db_connection, put_db_connection

logger = structlog.get_logger(__name__)

# Environment variables for Redis
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))

DSM_EVENTS_STREAM_NAME = "dsm:events"
CONSUMER_GROUP = "backlog_service_group"
CONSUMER_NAME = f"backlog_service_consumer_{str(uuid.uuid4())}"


class RedisConsumer:
    def __init__(self):
        self.redis_client = None
        self.running = False

    async def connect(self):
        try:
            self.redis_client = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("Redis consumer connected successfully.")
        except redis.ConnectionError as e:
            logger.error("Redis consumer failed to connect", error=str(e))
            self.redis_client = None

    async def start_consuming(self):
        if not self.redis_client:
            await self.connect()
            if not self.redis_client:
                return

        try:
            await self.redis_client.xgroup_create(
                DSM_EVENTS_STREAM_NAME, CONSUMER_GROUP, id="0", mkstream=True
            )
            logger.info("Consumer group created or already exists.", group=CONSUMER_GROUP)
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                logger.error("Error creating consumer group", error=str(e))
                return

        self.running = True
        logger.info("Event consumer started...", stream=DSM_EVENTS_STREAM_NAME)
        while self.running:
            try:
                messages = await self.redis_client.xreadgroup(
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    {DSM_EVENTS_STREAM_NAME: ">"},
                    count=1,
                    block=1000,
                )

                for _, message_list in messages:
                    for message_id, message_data in message_list:
                        await self.process_message(message_id, message_data)

            except redis.ConnectionError as e:
                logger.error("Redis connection lost. Reconnecting...", error=str(e))
                await self.connect()
            except Exception as e:
                logger.error("An unexpected error occurred in the consumer loop", error=str(e))
                await asyncio.sleep(5)

    async def process_message(self, message_id, message_data):
        try:
            event_data = json.loads(message_data["data"])
            event_type = event_data.get("event_type")

            if event_type == "SprintStarted":
                await self.handle_sprint_started(event_data["payload"])

            await self.redis_client.xack(DSM_EVENTS_STREAM_NAME, CONSUMER_GROUP, message_id)
        except json.JSONDecodeError:
            logger.error("Failed to decode JSON from message", message_id=message_id)
        except Exception as e:
            logger.error(
                "Error processing message",
                message_id=message_id,
                error=str(e),
            )

    async def handle_sprint_started(self, payload):
        sprint_id = payload.get("sprint_id")
        task_ids = payload.get("tasks", [])

        if not sprint_id or not task_ids:
            logger.warning("SprintStarted event is missing sprint_id or tasks", payload=payload)
            return

        logger.info(
            "Processing SprintStarted event",
            sprint_id=sprint_id,
            task_count=len(task_ids),
        )

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            for task_id in task_ids:
                cur.execute(
                    """
                    UPDATE tasks
                    SET status = 'assigned_to_sprint', sprint_id = %s
                    WHERE task_id = %s
                    """,
                    (sprint_id, task_id),
                )
            conn.commit()
            logger.info(
                "Tasks updated for sprint",
                sprint_id=sprint_id,
                updated_tasks=len(task_ids),
            )
        except (Exception, psycopg2.DatabaseError) as e:
            logger.error(
                "Database error while handling SprintStarted event",
                error=str(e),
                sprint_id=sprint_id,
            )
            if conn:
                conn.rollback()
        finally:
            if conn:
                cur.close()
                put_db_connection(conn)

    def stop(self):
        self.running = False
        logger.info("Redis consumer stopping...")
