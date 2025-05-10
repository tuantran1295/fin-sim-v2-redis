# listen_message.py
import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
pubsub = r.pubsub()
pubsub.subscribe("test_channel")

print("Listening on 'test_channel'... (Press Ctrl+C to exit)")

try:
    for message in pubsub.listen():
        if message['type'] == 'message':
            print(f"Received message: {message['data']}")
            #print(f"Decoded message: {message['data'].decode('utf-8')}")

    message = pubsub.get_message()
    if message and message['type'] == 'message':
        print(f"GET message: {message['data']}")
        print(f"Decoded GET message: {message['data'].decode('utf-8')}")
except KeyboardInterrupt:
    print("\nStopped listening.")