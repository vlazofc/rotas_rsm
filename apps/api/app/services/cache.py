"""Small fail-open Redis cache for expensive read-only projections."""
import json
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

_redis = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=0.2,
    socket_timeout=0.2,
)


def get_json(key: str) -> Any | None:
    try:
        value = _redis.get(key)
        return json.loads(value) if value is not None else None
    except (RedisError, json.JSONDecodeError):
        return None


def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    try:
        _redis.setex(key, ttl_seconds, json.dumps(value, separators=(",", ":"), ensure_ascii=False))
    except (RedisError, TypeError):
        # Redis is an optimization; an outage must not take down the API.
        return
