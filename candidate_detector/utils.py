from datetime import datetime
import re

def parse_time(time_str: str) -> datetime:
    """Parses an ISO timestamp string."""
    try:
        # Handles typical ISO format returned in the JSON
        if time_str.endswith("Z"):
            time_str = time_str[:-1] + "+00:00"
        return datetime.fromisoformat(time_str)
    except Exception:
        # Fallback to current time if parsing fails to avoid crashes
        return datetime.now()

def duration_to_seconds(duration_str: str) -> int:
    """Converts a duration string like '00:15:56' into total seconds."""
    try:
        parts = duration_str.split(":")
        if len(parts) == 3:
            h, m, s = map(int, parts)
            return h * 3600 + m * 60 + s
        return 0
    except Exception:
        return 0
