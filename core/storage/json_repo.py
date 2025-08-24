from __future__ import annotations

import json
import shutil
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Generic, Iterable, List, Mapping, Optional, TypeVar, Union
from uuid import uuid4

try:
    # Pydantic v2
    from pydantic import BaseModel
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    _HAS_PYDANTIC = False
    class BaseModel:  # type: ignore
        def model_dump(self) -> Dict[str, Any]:
            return dict(self.__dict__)


T = TypeVar("T", bound=Union[BaseModel, Mapping[str, Any]])


def _json_default(o: Any) -> Any:
    """Sérialiseur JSON: date/datetime -> ISO 8601, sinon str(o)."""
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


class JsonRepository(Generic[T]):
    """
    Repo JSON générique (liste d'objets dict/BaseModel) avec clé primaire configurable.
    - Stockage dans un fichier JSON (liste).
    - Backup horodaté avant écriture.
    - Sérialisation datetime -> ISO 8601.
    """

    def __init__(self, filepath: Union[str, Path], entity_name: str = "entity", key: str = "id") -> None:
        self.filepath = Path(filepath)
        self.entity_name = entity_name
        self.key = key
        self._lock = threading.Lock()

        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        if not self.filepath.exists():
            self._write_raw([])

    # ---------------- I/O bas niveau ---------------- #

    def _read_raw(self) -> List[Dict[str, Any]]:
        try:
            with self.filepath.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            return data
        except FileNotFoundError:
            return []
        except json.JSONDecodeError:
            # Fichier corrompu → sauvegarde et repart sur liste vide
            try:
                backup = self.filepath.with_suffix(".corrupt.json")
                shutil.copy2(self.filepath, backup)
            except Exception:
                pass
            return []

    def _write_raw(self, data: Iterable[Mapping[str, Any]]) -> None:
        with self._lock:
            # backup
            if self.filepath.exists():
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                backup = self.filepath.with_suffix(f".{ts}.bak.json")
                try:
                    shutil.copy2(self.filepath, backup)
                except Exception:
                    pass
            # write
            with self.filepath.open("w", encoding="utf-8") as f:
                json.dump(list(data), f, ensure_ascii=False, indent=2, default=_json_default)

    # ---------------- Helpers ---------------- #

    @staticmethod
    def _to_dict(item: T) -> Dict[str, Any]:
        if _HAS_PYDANTIC and isinstance(item, BaseModel):
            return item.model_dump()
        if hasattr(item, "model_dump"):
            return item.model_dump()  # BaseModel-like
        if isinstance(item, Mapping):
            return dict(item)
        return dict(item.__dict__)  # type: ignore[arg-type]

    # ---------------- CRUD ---------------- #

    def list_all(self) -> List[Dict[str, Any]]:
        return self._read_raw()

    def get_by_id(self, obj_id: Any) -> Optional[Dict[str, Any]]:
        k = self.key
        for it in self._read_raw():
            if str(it.get(k)) == str(obj_id):
                return it
        return None

    def add(self, item: T) -> Dict[str, Any]:
        record = self._to_dict(item)
        k = self.key
        if not record.get(k):
            record[k] = uuid4().hex if k == "id" else uuid4().hex
        data = self._read_raw()
        if any(str(d.get(k)) == str(record[k]) for d in data):
            raise ValueError(f"{self.entity_name} with {k}={record[k]} already exists")
        data.append(record)
        self._write_raw(data)
        return record

    def update(self, item: T) -> Dict[str, Any]:
        record = self._to_dict(item)
        k = self.key
        obj_id = record.get(k)
        if not obj_id:
            raise ValueError(f"Cannot update {self.entity_name} without '{k}'")
        data = self._read_raw()
        for idx, existing in enumerate(data):
            if str(existing.get(k)) == str(obj_id):
                merged = {**existing, **record}
                data[idx] = merged
                self._write_raw(data)
                return merged
        raise ValueError(f"{self.entity_name} with {k}={obj_id} not found")

    def upsert(self, item: T) -> Dict[str, Any]:
        try:
            return self.update(item)
        except ValueError:
            return self.add(item)

    def delete(self, obj_id: Any) -> bool:
        k = self.key
        data = self._read_raw()
        new_data = [d for d in data if str(d.get(k)) != str(obj_id)]
        changed = len(new_data) != len(data)
        if changed:
            self._write_raw(new_data)
        return changed

    # ---------------- Recherches (compat .find) ---------------- #

    def find(self, predicate: Callable[[Dict[str, Any]], bool]) -> List[Dict[str, Any]]:
        """
        Retourne tous les enregistrements pour lesquels predicate(record) == True.
        Compatible avec les usages: repo.find(lambda d: d.get("quote_id") == qid)
        """
        rows = self._read_raw()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                if predicate(r):
                    out.append(r)
            except Exception:
                # on ignore les exceptions dans le prédicat pour robustesse
                continue
        return out

    def find_one(self, predicate: Callable[[Dict[str, Any]], bool]) -> Optional[Dict[str, Any]]:
        """Premier enregistrement qui matche predicate, ou None."""
        rows = self._read_raw()
        for r in rows:
            try:
                if predicate(r):
                    return r
            except Exception:
                continue
        return None
