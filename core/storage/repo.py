from __future__ import annotations
import json, os, tempfile, threading
from typing import Any, Callable

_lock = threading.Lock()

class JsonRepository:
    def __init__(self, file_path: str, key: str = "id"):
        self.file_path = file_path
        self.key = key
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        if not os.path.exists(file_path):
            self._write([])

    def _read(self) -> list[dict]:
        if not os.path.exists(self.file_path):
            return []
        with open(self.file_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []

    def _write(self, data: list[dict]):
        tmp_fd, tmp_path = tempfile.mkstemp(prefix="tmp", suffix=".json", dir=os.path.dirname(self.file_path))
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.file_path)
        finally:
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except: pass

    def list_all(self) -> list[dict]:
        return self._read()

    def add(self, item: dict):
        with _lock:
            data = self._read()
            data.append(item)
            self._write(data)

    def update(self, item: dict):
        with _lock:
            data = self._read()
            idx = next((i for i, d in enumerate(data) if d.get(self.key)==item.get(self.key)), None)
            if idx is None:
                raise KeyError("Item not found")
            data[idx] = item
            self._write(data)

    def delete(self, item_id: str):
        with _lock:
            data = [d for d in self._read() if d.get(self.key)!=item_id]
            self._write(data)

    def find(self, predicate: Callable[[dict], bool]) -> list[dict]:
        return [d for d in self._read() if predicate(d)]
