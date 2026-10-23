"""Small, cache-backed fixed-window rate limiter.

Uses Django's database cache so limits are shared by all gunicorn workers.
Tune the numbers in one place (here) or per call site in views.py.
"""

import time

from django.conf import settings
from django.core.cache import cache


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int = 60):
        self.retry_after = max(1, int(retry_after))
        super().__init__("Rate limit exceeded")


def client_ip(request) -> str:
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")


def enforce(request, bucket: str, limit: int, window: int, ident: str = "") -> int:
    """Count one hit. Raises RateLimitExceeded when over the limit.

    ``window`` is in seconds. Keys roll over automatically, so no cleanup job
    is needed.
    """
    who = ident or client_ip(request)
    slot = int(time.time() // window)
    key = f"rl:{bucket}:{who}:{slot}"

    try:
        count = cache.incr(key)
    except ValueError:
        cache.add(key, 1, window + 5)
        count = cache.get(key, 1)

    if count > limit:
        raise RateLimitExceeded(window - int(time.time()) % window)
    return count
