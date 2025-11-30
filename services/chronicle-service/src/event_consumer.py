import asyncio
import json
import logging
import os
import redis
import threading
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RedisConsumer:
    def __init__(self, service_name: str, stream_name: str, handler_function):
        self.service_name = service_name
        self.stream_name = stream_name
        self.group_name = f"{service_name}-group"
        self.consumer_name = f"{service_name}-consumer-{os.getpid()}"
        self.handler_function = handler_function
        self.redis_client = None
        self.running = False
        self.thread = None
        self.reconnect_interval = 5 # seconds

    def _connect_redis(self):
        #redis_host = os.getenv("REDIS_HOST", "redis")
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", 6379))
        redis_db = int(os.getenv("REDIS_DB", 0))
        redis_password = os.getenv("REDIS_PASSWORD", None)
        logger.info(f"Testing ::  connected to Redis with  {redis_host}:{redis_port}")

        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                password=redis_password,
                decode_responses=True
            )
            self.redis_client.ping()
            logger.info(f"Successfully connected to Redis at {redis_host}:{redis_port}")
            return True
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Could not connect to Redis: {e}")
            self.redis_client = None
            return False

#####
    def _ensure_consumer_group(self):
        if not self.redis_client:
           logger.error("Redis client is None in _ensure_consumer_group")
           return False
        try:
            self.redis_client.xgroup_create(self.stream_name, self.group_name, id='0', mkstream=True)
            logger.info(f"✅ Consumer group '{self.group_name}' created for stream '{self.stream_name}'.")
            return True
        except redis.exceptions.ResponseError as e:
            logger.error(f"❌ ResponseError during xgroup_create: {e}")
            if "BUSYGROUP" in str(e):
                logger.info(f"ℹ️ Consumer group '{self.group_name}' already exists.")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error in _ensure_consumer_group: {e}", exc_info=True)
            return False


##### OLD

#    def _ensure_consumer_group1(self):
#        if not self.redis_client:
#            return False
#        try:
#            self.redis_client.xgroup_create(self.stream_name, self.group_name, id='0', mkstream=True)
#            logger.info(f"Consumer group '{self.group_name}' created or already exists for stream '{self.stream_name}'.")
#            return True
#        except redis.exceptions.ResponseError as e:
#            if "BUSYGROUP" in str(e):
#                logger.info(f"Consumer group '{self.group_name}' already exists.")
#                return True
#            else:
#                logger.error(f"Error ensuring consumer group: {e}")
#                return False
#        except Exception as e:
#            logger.error(f"An unexpected error occurred while ensuring consumer group: {e}")
#            return False


### new ###
    def _listen_for_events(self):
        while self.running:
            # Attempt to connect if not already connected
            if not self.redis_client:
                if not self._connect_redis():
                    logger.warning("❌ _connect_redis failed. Retrying...")
                    time.sleep(self.reconnect_interval)
                    continue

                if not self._ensure_consumer_group():
                    logger.warning("❌ _ensure_consumer_group failed. Retrying...")
                    time.sleep(self.reconnect_interval)
                    continue

                logger.info("✅ Connected and consumer group ensured. Listening for events...")

            try:
                messages = self.redis_client.xreadgroup(
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
                                # Decode and process the message
                                event_data = {k: v for k, v in message_data.items()}
                                event_payload = json.loads(event_data.get('payload', '{}'))
                                event_type = event_payload.get('event_type')

                                logger.info(f"📥 Received event: ID={message_id}, Type={event_type}")

                                if event_type == "SprintStarted":
                                    self.handler_function(event_payload)
                                else:
                                    logger.info(f"Skipping unknown event type: {event_type}")

                                # Acknowledge message regardless
                                self.redis_client.xack(self.stream_name, self.group_name, message_id)
                                logger.info(f"✅ Acknowledged event ID: {message_id}")
                            except Exception as e:
                                logger.error(f"❌ Error processing message ID {message_id}: {e}", exc_info=True)
                                # Acknowledge to avoid reprocessing bad message
                                self.redis_client.xack(self.stream_name, self.group_name, message_id)
                else:
                    pass # Suppressed "No new messages." log

            except redis.exceptions.ConnectionError as e:
                logger.error(f"🔌 Redis connection lost: {e}")
                self.redis_client = None
                time.sleep(self.reconnect_interval)
            except Exception as e:
                logger.error(f"❌ Unexpected error in event loop: {e}", exc_info=True)
                time.sleep(self.reconnect_interval)


### new end ###

#old backup
    def _listen_for_events1(self):
        while self.running:
###
            if not self.redis_client:
               logger.warning("Redis client is not initialized.")
            if not self._connect_redis():
               logger.warning("Failed to connect to Redis.")
            if not self._ensure_consumer_group():
               logger.warning("Failed to ensure consumer group.")
            if not self.redis_client:
               logger.warning("Redis client is not initialized.")
            if not self._connect_redis():
               logger.warning("Failed to connect to Redis.")
            if not self._ensure_consumer_group():
               logger.warning("Failed to ensure consumer group.")

####
            if not self.redis_client:
                logger.warning("Redis client is None. Attempting to connect.")
            if not self._connect_redis():
                logger.warning("❌ _connect_redis failed. Retrying...")
                time.sleep(self.reconnect_interval)
                continue
            if not self._ensure_consumer_group():
                logger.warning("❌ _ensure_consumer_group failed. Retrying...")
                time.sleep(self.reconnect_interval)
                continue

            logger.info("✅ Connected and consumer group ensured. Listening for events...")
####

            if not self.redis_client or not self._connect_redis() or not self._ensure_consumer_group():
                logger.warning(f"Redis connection or group setup failed. Retrying in {self.reconnect_interval} seconds...")
                time.sleep(self.reconnect_interval)
                continue



            try:
                # Read new messages, block for 1 second if no new messages
                messages = self.redis_client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    {self.stream_name: '>'}, # Read new messages
                    count=1,
                    block=1000 # Block for 1000 milliseconds
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
                                    self.handler_function(event_payload)
                                    self.redis_client.xack(self.stream_name, self.group_name, message_id)
                                    logger.info(f"Acknowledged event ID: {message_id}")
                                else:
                                    logger.info(f"Skipping unknown event type: {event_type}")
                                    self.redis_client.xack(self.stream_name, self.group_name, message_id) # Acknowledge to avoid reprocessing
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to decode JSON payload for message ID {message_id}: {e}")
                                # Potentially NACK or move to DLQ if supported, for now, acknowledge to prevent re-processing bad messages
                                self.redis_client.xack(self.stream_name, self.group_name, message_id)
                            except Exception as e:
                                logger.error(f"Error processing message ID {message_id}: {e}", exc_info=True)
                                # Do not acknowledge, so it can be reprocessed or handled manually
                else:
                    logger.debug("No new messages.")

            except redis.exceptions.ConnectionError as e:
                logger.error(f"Redis connection lost: {e}. Attempting to reconnect...")
                self.redis_client = None
                time.sleep(self.reconnect_interval)
            except Exception as e:
                logger.error(f"An unexpected error occurred in event loop: {e}", exc_info=True)
                time.sleep(self.reconnect_interval)

    def start(self):
        if self.running:
            logger.warning("Redis consumer is already running.")
            return

        logger.info(f"Starting Redis consumer for service '{self.service_name}' on stream '{self.stream_name}'...")
        self.running = True
        self.thread = threading.Thread(target=self._listen_for_events, daemon=True)
        self.thread.start()
        logger.info("Event consumer started in background thread.")

    def stop(self):
        if not self.running:
            logger.warning("Redis consumer is not running.")
            return

        logger.info("Stopping Redis consumer...")
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5) # Give it some time to finish current processing
            if self.thread.is_alive():
                logger.warning("Consumer thread did not terminate gracefully.")
        if self.redis_client:
            self.redis_client.close()
        logger.info("Redis consumer stopped.")

if __name__ == "__main__":
    # This block is for testing the consumer independently
    # In a real application, this would be integrated into the main app.py
    def test_handler(payload):
        print(f"Test Handler received payload: {payload}")

    # Set dummy environment variables for local testing
    os.environ["REDIS_HOST"] = "localhost" # Or your local Redis IP
    os.environ["REDIS_PORT"] = "6379"
    os.environ["REDIS_DB"] = "0"

    consumer = RedisConsumer(
        service_name="test-chronicle-service",
        stream_name="dsm:events",
        handler_function=test_handler
    )
    consumer.start()

    try:
        # Keep the main thread alive to allow the consumer thread to run
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        consumer.stop()
        print("Exiting.")
