import redis
from dotenv import load_dotenv
import os
import logging

load_dotenv()

class RedisManager:
    def __init__(self):
        self.redis_connected = False
        try:
            self.r = redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                password=os.getenv("REDIS_PASSWORD", None),
                socket_connect_timeout=3,
                decode_responses = True
            )
            self.r.ping()  # Test connection
            self.redis_connected = True
        except redis.exceptions.ConnectionError as e:
            logging.warning(f"Redis not connected: {e}")
            self.r = None

    def publish_update(self, channel, message):
        if self.redis_connected:
            try:
                self.r.publish(channel, message)
            except redis.exceptions.RedisError as e:
                logging.error(f"Redis publish error: {e}")

    def subscribe_to_channel(self, channel):
        if self.redis_connected:
            try:
                pubsub = self.r.pubsub()
                pubsub.subscribe(channel)
                return pubsub
            except redis.exceptions.RedisError as e:
                logging.error(f"Redis subscribe error: {e}")
        return DummyPubSub()

class DummyPubSub:
    """Fallback when Redis isn't available"""
    def get_message(self):
        return None
    def unsubscribe(self, channel):
        pass

# Create single instance
redis_manager = RedisManager()
