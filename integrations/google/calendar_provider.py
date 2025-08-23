from datetime import datetime
from typing import Optional

def create_event(summary: str, start: datetime, end: datetime, location: str|None=None, description: str|None=None) -> Optional[str]:
    # TODO: call Google Calendar API, return google_event_id
    return None

def update_event(google_event_id: str, **kwargs) -> bool:
    # TODO
    return False

def delete_event(google_event_id: str) -> bool:
    # TODO
    return False
