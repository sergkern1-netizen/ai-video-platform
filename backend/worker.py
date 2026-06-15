import os
from dotenv import load_dotenv
load_dotenv()

from redis import Redis
from rq import Worker, Queue

if __name__ == "__main__":
    redis_conn = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    q = Queue(connection=redis_conn)
    worker = Worker([q], connection=redis_conn)
    worker.work()
