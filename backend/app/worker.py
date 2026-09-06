from redis import Redis
from rq import Queue

from .config import settings


redis = Redis.from_url(settings.redis_url)
queue = Queue("tingjian", connection=redis, default_timeout=7200)


def enqueue(func, *args):
    return queue.enqueue(func, *args, job_timeout=7200, result_ttl=86400, failure_ttl=604800)

