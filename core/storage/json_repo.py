from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generic, Iterable, List, Mapping, Optional, TypeVar, Union
from uuid import uuid4

try:
    # Pydantic v2
    from pydantic import BaseModel
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    _HAS_PYDANTIC = False
    class BaseModel:  # type: ignore
        def model_dump(self) -> Dict[str, Any]:  # fallback
            return dict(self.__dict__)


T = TypeVar("T", bound=Union[BaseModel, Mapping[str, Any]])


class JsonRepository(Generic[T]):
    """
    Repo JSON générique.
    - Stocke une liste d'objets (dict ou BaseModel Pydantic) dans un fichier JSON.
    - Chaque objet possède un champ 'key' (par défaut 'id').
    - Gère backup horodaté avant écriture.
    """

    def __init__(self, filepath: Union[str, Path], entity_name: str = "entity", key: str = "id") -> None:
        self.filepath = Path(filepath)
        self.entity_name = entity_name
        self.key = key  # clé primaire (ex: 'id' par défaut)
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
            # Fichier corrompu → sauvegarde et repars vide
            backup = self.filepath.with_suffix(".corrupt.json")
            try:
                shutil.copy2(self.filepath, backup)
            except Exception:
                pass
            return []

    def _write_raw(self, data: Iterable[Mapping[str, Any]]) -> None:
        # backup
        if self.filepath.exists():
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = self.filepath.with_suffix(f".{ts}.bak.json")
            try:
                shutil.copy2(self.filepath, backup)
            except Exception:
                pass
        with self.filepath.open("w", encoding="utf-8") as f:
            json.dump(list(data), f, ensure_ascii=False, indent=2)

    # ---------------- Helpers ---------------- #

    @staticmethod
    def _to_dict(item: T) -> Dict[str, Any]:
        if _HAS_PYDANTIC and isinstance(item, BaseModel):
            return item.model_dump()  # pydantic v2
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
            # si la clé primaire est 'id', on génère un UUID par défaut
            record[k] = uuid4().hex if k == "id" else uuid4().hex
        data = self._read_raw()
        # éviter doublon
        if any(str(d.get(k)) == str(record[k]) for d in data):
            raise ValueError(f"{self.entity_name} with {k}={record[k]} already exists")
        data.append(record)
        self._write_raw(data)
        return record

    def update(self, item: T) -> Dict[str, Any]:
        """
        Met à jour sur clé primaire `self.key`. Soulève ValueError si clé absente ou introuvable.
        """
        record = self._to_dict(item)
        k = self.key
        obj_id = record.get(k)
        if not obj_id:
            raise ValueError(f"Cannot update {self.entity_name} without '{k}'")
        data = self._read_raw()
        for idx, existing in enumerate(data):
            if str(existing.get(k)) == str(obj_id):
                merged = {**existing, **record}  # merge champ à champ
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
