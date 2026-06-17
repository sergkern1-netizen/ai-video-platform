import os
from dotenv import load_dotenv
load_dotenv()

from redis import Redis
from rq import Queue, SimpleWorker
from rq.timeouts import TimerDeathPenalty

if __name__ == "__main__":
    redis_conn = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    q = Queue(connection=redis_conn)
    worker = SimpleWorker([q], connection=redis_conn)
    worker.death_penalty_class = TimerDeathPenalty
    worker.work()
