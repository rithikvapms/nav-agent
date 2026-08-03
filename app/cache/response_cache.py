from cachetools import TTLCache

response_cache = TTLCache(
    maxsize=500,
    ttl=600
)