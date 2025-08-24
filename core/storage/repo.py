from __future__ import annotations
import json, os, tempfile, threading
from typing import Callable, List, Dict, Any
from datetime import datetime, date

_lock = threading.Lock()

def _json_default(o: Any):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    # Laisse json lever une erreur pour les autres types non gérés
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

class JsonRepository:
    def __init__(self, path: str, key: str = "id"):
        self.path = path
        self.key = key
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump([], f)
        self._load()

    def _load(self):
        with open(self.path, "r", encoding="utf-8") as f:
            try:
                self.data: List[Dict[str, Any]] = json.load(f)
            except Exception:
                self.data = []

    def _save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self.data)

    def find(self, pred: Callable[[Dict[str, Any]], bool]) -> List[Dict[str, Any]]:
        return [d for d in self.data if pred(d)]

    def _index_of_key(self, key_value: Any) -> int:
        for i, d in enumerate(self.data):
            if d.get(self.key) == key_value:
                return i
        return -1

    def add(self, item: Dict[str, Any]) -> None:
        self.data.append(item)
        self._save()

    def update(self, item: Dict[str, Any]) -> None:
        key_value = item.get(self.key)
        idx = self._index_of_key(key_value)
        if idx < 0:
            raise KeyError("Item not found")
        self.data[idx] = item
        self._save()

    def upsert(self, item: Dict[str, Any]) -> None:
        """Met à jour si l'item existe (même id), sinon l'ajoute."""
        key_value = item.get(self.key)
        if key_value is None:
            # si pas d'id => ajout
            self.add(item)
            return
        idx = self._index_of_key(key_value)
        if idx < 0:
            self.add(item)
        else:
            self.data[idx] = item
            self._save()

    def delete(self, key_value: Any) -> None:
        idx = self._index_of_key(key_value)
        if idx < 0:
            raise KeyError("Item not found")
        self.data.pop(idx)
        self._save()
