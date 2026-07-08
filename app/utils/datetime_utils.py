from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def from_unix_timestamp(timestamp: int | None) -> datetime | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
