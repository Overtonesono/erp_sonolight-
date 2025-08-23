from __future__ import annotations
import os, json
from datetime import datetime, timedelta
from typing import Optional

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data"))
SETTINGS_JSON = os.path.join(DATA_DIR, "settings.json")
EXPORTS_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "exports", "agenda"))

class CalendarService:
    def __init__(self):
        os.makedirs(EXPORTS_DIR, exist_ok=True)

    def _load_json(self, path: str):
        if not os.path.exists(path): return None
        try:
            with open(path, "r", encoding="utf-8") as f: return json.load(f)
        except Exception: return None

    def create_event_for_quote(self, *, title: str, date_only: datetime, description: str) -> str:
        # Tentative Google
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            SCOPES = ["https://www.googleapis.com/auth/calendar"]
            token_path = os.path.join(DATA_DIR, "token.json")
            cred_path = os.path.join(DATA_DIR, "credentials.json")
            creds = None
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    from google.auth.transport.requests import Request
                    creds.refresh(Request())
                else:
                    if not os.path.exists(cred_path):
                        raise RuntimeError("credentials.json manquant pour Google Calendar")
                    flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())

            service = build("calendar", "v3", credentials=creds)
            start = datetime(date_only.year, date_only.month, date_only.day)
            end = start + timedelta(days=1)
            body = {
                "summary": title,
                "description": description,
                "start": {"date": start.date().isoformat()},  # all-day
                "end": {"date": end.date().isoformat()},
            }
            settings = self._load_json(SETTINGS_JSON) or {}
            calendar_id = (settings.get("calendar", {}) or {}).get("default_calendar_id", "primary")
            event = service.events().insert(calendarId=calendar_id, body=body).execute()
            return f"Créé dans Google Agenda (id: {event.get('id')})"
        except Exception:
            # Fallback ICS
            try:
                from ics import Calendar, Event
                c = Calendar()
                e = Event()
                e.name = title
                e.begin = date_only
                e.make_all_day()
                e.description = description
                c.events.add(e)
                path = os.path.join(EXPORTS_DIR, f"{title.replace(' ', '_')}.ics")
                with open(path, "w", encoding="utf-8") as f:
                    f.writelines(c)
                return f"ICS généré : {path}"
            except Exception as e:
                raise RuntimeError(f"Impossible de créer l'évènement: {e}")
