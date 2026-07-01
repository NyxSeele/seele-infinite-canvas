"""统一控制台日志：保证 uvicorn 启动后 INFO 级别可见，并抑制高频 access 刷屏。"""

from __future__ import annotations

import logging
import os
import re
import sys
import time

_ACCESS_RE = re.compile(r'"([A-Z]+)\s+(/[^\s"]+)"\s+(\d+)')

QUIET_ACCESS_PATHS = (
    "/api/teams/mine",
    "/api/canvas/projects",
    "/api/auth/me",
    "/api/media/ticket",
)


class ThrottledAccessLogFilter(logging.Filter):
    """高频 2xx 请求合并输出，4xx/5xx 始终打印。"""

    def __init__(
        self,
        *,
        quiet_paths: tuple[str, ...] = QUIET_ACCESS_PATHS,
        interval: float = 15.0,
    ) -> None:
        super().__init__()
        self.quiet_paths = quiet_paths
        self.interval = interval
        self._last_logged: dict[str, float] = {}
        self._suppressed: dict[str, int] = {}

    def _match_quiet(self, path: str) -> str | None:
        path_only = path.split("?", 1)[0]
        for prefix in self.quiet_paths:
            if path_only == prefix:
                return prefix
        return None

    def filter(self, record: logging.LogRecord) -> bool:
        if os.environ.get("UVICORN_ACCESS_LOG", "throttle").lower() == "off":
            return False

        msg = record.getMessage()
        match = _ACCESS_RE.search(msg)
        if not match:
            return True

        _method, path, status_str = match.groups()
        status = int(status_str)
        if status >= 400:
            return True

        quiet_key = self._match_quiet(path)
        if not quiet_key:
            return True

        now = time.monotonic()
        last = self._last_logged.get(quiet_key, 0.0)
        if now - last < self.interval:
            self._suppressed[quiet_key] = self._suppressed.get(quiet_key, 0) + 1
            return False

        suppressed = self._suppressed.pop(quiet_key, 0)
        if suppressed:
            record.msg = f"{msg}  (+{suppressed} 条同类请求已折叠)"
            record.args = ()
        self._last_logged[quiet_key] = now
        return True


_ACCESS_FILTER = ThrottledAccessLogFilter()


def apply_access_log_filters() -> None:
    """uvicorn 启动后会重置 logging，需在 lifespan 里再次挂载过滤器。"""
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.filters = [
        item for item in access_logger.filters if not isinstance(item, ThrottledAccessLogFilter)
    ]
    access_logger.addFilter(_ACCESS_FILTER)
    for handler in access_logger.handlers:
        handler.filters = [
            item for item in handler.filters if not isinstance(item, ThrottledAccessLogFilter)
        ]
        handler.addFilter(_ACCESS_FILTER)


def build_uvicorn_log_config() -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "throttled_access": {
                "()": "core.logging_setup.ThrottledAccessLogFilter",
            }
        },
        "formatters": {
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(levelprefix)s %(message)s",
                "use_colors": None,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s',
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "formatter": "access",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "filters": ["throttled_access"],
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
        },
    }


def configure_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)

    apply_access_log_filters()
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).setLevel(level)


def studio_print(tag: str, message: str) -> None:
    """高信号一行日志，始终打印到 stdout（不依赖 logging 配置）。"""
    print(f"[AIStudio:{tag}] {message}", flush=True)
