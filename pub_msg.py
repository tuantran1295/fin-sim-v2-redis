# publish_message.py
import redis
import time

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

channel = "test_channel"
message = "Hello from Publisher"

print(f"Publishing to '{channel}': {message}")
r.publish(channel, message)