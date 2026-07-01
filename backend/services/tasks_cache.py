import time

from core.config import settings

_tasks_cache: dict = {"data": None, "ts": 0.0}


def invalidate_tasks_cache() -> None:
    _tasks_cache["data"] = None
    _tasks_cache["ts"] = 0.0


def get_cached_tasks():
    now = time.time()
    if (
        _tasks_cache["data"] is not None
        and now - _tasks_cache["ts"] < settings.tasks_cache_ttl
    ):
        return _tasks_cache["data"], True
    return None, False


def set_cached_tasks(tasks: list) -> None:
    _tasks_cache["data"] = tasks
    _tasks_cache["ts"] = time.time()
