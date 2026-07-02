from datetime import datetime, timezone


def to_utc_iso(dt: datetime | None) -> str | None:
    """Serialize datetime as UTC ISO 8601 with Z suffix."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    text = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return f"{text[:-3]}Z"
