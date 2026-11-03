"""Time helpers. All internal time logic uses timezone-aware datetimes in UTC."""

from datetime import datetime


def require_aware(value: datetime, name: str) -> None:
    """Reject naive datetimes; a time zone is never assumed."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must include a UTC offset.")
