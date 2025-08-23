from __future__ import annotations
from typing import List, Optional
import os

from pydantic import ValidationError

from core.models.client import Client
from core.storage.repo import JsonRepository


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data"))
CLIENTS_JSON = os.path.join(DATA_DIR, "clients.json")


class ClientService:
    def __init__(self, path: str = CLIENTS_JSON):
        self.repo = JsonRepository(path, key="id")

    def list_clients(self) -> List[Client]:
        items = self.repo.list_all()
        out: List[Client] = []
        for d in items:
            try:
                out.append(Client(**d))
            except ValidationError:
                # On ignore les entrées invalides pour ne pas casser l'UI
                continue
        return out

    def add_client(self, client: Client) -> Client:
        self.repo.add(client.model_dump())
        return client

    def update_client(self, client: Client) -> Client:
        self.repo.update(client.model_dump())
        return client

    def delete_client(self, client_id: str) -> None:
        self.repo.delete(client_id)

    def get_by_id(self, client_id: str) -> Optional[Client]:
        matches = self.repo.find(lambda d: d.get("id") == client_id)
        if not matches:
            return None
        try:
            return Client(**matches[0])
        except ValidationError:
            return None
