import time
import random

messages = [
    "INFO: System normal",
    "WARNING: High CPU usage",
    "ERROR: Disk full",
    "DEBUG: Connection established",
    "CRITICAL: Service down",
]

while True:
    msg = random.choice(messages)
    print(f"{time.ctime()} - {msg}")
    time.sleep(random.uniform(0.1, 1.0))
