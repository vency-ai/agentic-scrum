import asyncio
import json
import os
import redis.asyncio
import redis.exceptions
import structlog
import logging

# Configure logging - set to INFO level to reduce debug noise
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = structlog.get_logger(__name__)

class RedisConsumer:
    def __init__(self, service_name: str, stream_name: str, handler_function):
        self.service_name = service_name
        self.stream_name = stream_name
        self.group_name = f"{service_name}-group"
        self.consumer_name = f"{service_name}-consumer-{os.getpid()}"
        self.handler_function = handler_function
        self.redis_client = None
        self.running = False
        self.reconnect_interval = 5 # seconds

    async def _connect_redis(self):
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = os.getenv("REDIS_PORT", "6379")
        redis_db = os.getenv("REDIS_DB", "0")
        redis_password = os.getenv("REDIS_PASSWORD", None)

        try:
            logger.debug(f"Attempting to connect to Redis with host={redis_host}, port={redis_port}, db={redis_db}, password_provided={bool(redis_password)}")
            self.redis_client = redis.asyncio.Redis(
                host=redis_host,
                port=int(redis_port),
                db=int(redis_db),
                password=redis_password,
                decode_responses=True
            )
            logger.debug("Redis client initialized. Attempting to ping...")
            await self.redis_client.ping()
            logger.info(f"Successfully connected to Redis at {redis_host}:{redis_port}")
            return True
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Redis: {e}")
            self.redis_client = None
            return False
        except Exception as e:
            logger.exception(f"An unexpected error occurred during Redis connection: {e}")
            self.redis_client = None
            return False

    async def _ensure_consumer_group(self):
        if not self.redis_client:
            return False
        try:
            await self.redis_client.xgroup_create(self.stream_name, self.group_name, id='0', mkstream=True)
            logger.info(f"Consumer group '{self.group_name}' created or already exists for stream '{self.stream_name}'.")
            return True
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Consumer group '{self.group_name}' already exists.")
                return True
            else:
                logger.error(f"Error ensuring consumer group: {e}")
                return False
        except Exception as e:
            logger.error(f"An unexpected error occurred while ensuring consumer group: {e}")
            return False

    async def _listen_for_events(self):
        while self.running:
            try:
                messages = await self.redis_client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    {self.stream_name: '>'},
                    count=1,
                    block=1000
                )

                if messages:
                    for stream, message_list in messages:
                        for message_id, message_data in message_list:
                            try:
                                event_data = {k.decode('utf-8'): v.decode('utf-8') for k, v in message_data.items()}
                                event_payload = json.loads(event_data.get('payload', '{}'))
                                event_type = event_payload.get('event_type')

                                logger.info(f"Received event: ID={message_id}, Type={event_type}")

                                if event_type == "SprintStarted":
                                    await self.handler_function(event_payload)
                                    await self.redis_client.xack(self.stream_name, self.group_name, message_id)
                                    logger.info(f"Acknowledged event ID: {message_id}")
                                else:
                                    logger.info(f"Skipping unknown event type: {event_type}")
                                    await self.redis_client.xack(self.stream_name, self.group_name, message_id)
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to decode JSON payload for message ID {message_id}: {e}")
                                await self.redis_client.xack(self.stream_name, self.group_name, message_id)
                            except Exception as e:
                                logger.error(f"Error processing message ID {message_id}: {e}", exc_info=True)
                else:
                    # Suppress "No new messages" to reduce log noise
                    pass

            except redis.exceptions.ConnectionError as e:
                logger.error(f"Redis connection lost: {e}. Attempting to reconnect...")
                self.redis_client = None
                # Attempt to reconnect and re-ensure group
                connected = await self._connect_redis()
                group_ensured = False
                if connected:
                    group_ensured = await self._ensure_consumer_group()

                if not connected or not group_ensured:
                    logger.error("Reconnection and group setup failed. Consumer will pause and retry.")
                    await asyncio.sleep(self.reconnect_interval)
                continue # Continue the while loop to try reading messages again after reconnection attempt
            except Exception as e:
                logger.error(f"An unexpected error occurred in event loop: {e}", exc_info=True)

    async def start(self):
        if self.running:
            logger.warning("Redis consumer is already running.")
            return

        logger.info(f"Starting Redis consumer for service '{self.service_name}' on stream '{self.stream_name}'...")
        self.running = True
        try:
            # Attempt initial connection and group setup once
            if not await self._connect_redis():
                logger.error("Initial Redis connection failed. Consumer will not start.")
                self.running = False
                return
            if not await self._ensure_consumer_group():
                logger.error("Initial Redis consumer group setup failed. Consumer will not start.")
                self.running = False
                return

            asyncio.create_task(self._listen_for_events())
            logger.info("Event consumer task initiated.")
        except Exception as e:
            logger.error(f"Failed to create asyncio task for event consumer: {e}")
            self.running = False
        logger.info("Event consumer started as an asyncio task.")

    async def stop(self):
        if not self.running:
            logger.warning("Redis consumer is not running.")
            return

        logger.info("Stopping Redis consumer...")
        self.running = False
        if self.redis_client:
            await self.redis_client.close()
        logger.info("Redis consumer stopped.")
