from flask_caching import Cache

cache = Cache()


def cache_get(key):
    """`cache.get`, or None when the cache can't be reached (tests, desk): a cache only ever saves work."""
    try:
        return cache.get(key)
    except Exception:
        return None


def cache_set(key, value, timeout):
    """`cache.set`, skipped when the cache can't be reached."""
    try:
        cache.set(key, value, timeout=timeout)
    except Exception:
        pass
