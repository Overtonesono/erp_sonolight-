from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generic, Iterable, List, Mapping, Optional, Type, TypeVar, Union
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
    - Chaque objet possède un champ 'id' (str).
    - Gère backup horodaté avant écriture.
    """

    def __init__(self, filepath: Union[str, Path], entity_name: str = "entity") -> None:
        self.filepath = Path(filepath)
        self.entity_name = entity_name
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
            shutil.copy2(self.filepath, backup)
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
            return item.model_dump()  # si BaseModel-like
        if isinstance(item, Mapping):
            return dict(item)
        # fallback (objet arbitraire)
        return dict(item.__dict__)  # type: ignore[arg-type]

    # ---------------- CRUD ---------------- #

    def list_all(self) -> List[Dict[str, Any]]:
        return self._read_raw()

    def get_by_id(self, obj_id: str) -> Optional[Dict[str, Any]]:
        for it in self._read_raw():
            if str(it.get("id")) == str(obj_id):
                return it
        return None

    def add(self, item: T) -> Dict[str, Any]:
        record = self._to_dict(item)
        if not record.get("id"):
            record["id"] = uuid4().hex
        data = self._read_raw()
        # éviter doublon
        if any(str(d.get("id")) == str(record["id"]) for d in data):
            raise ValueError(f"{self.entity_name} with id={record['id']} already exists")
        data.append(record)
        self._write_raw(data)
        return record

    def update(self, item: T) -> Dict[str, Any]:
        """
        Met à jour sur clé 'id'. Soulève ValueError si id absent ou introuvable.
        """
        record = self._to_dict(item)
        obj_id = record.get("id")
        if not obj_id:
            raise ValueError(f"Cannot update {self.entity_name} without 'id'")
        data = self._read_raw()
        for idx, existing in enumerate(data):
            if str(existing.get("id")) == str(obj_id):
                # merge champ à champ (préserve champs inconnus)
                merged = {**existing, **record}
                data[idx] = merged
                self._write_raw(data)
                return merged
        raise ValueError(f"{self.entity_name} with id={obj_id} not found")

    def upsert(self, item: T) -> Dict[str, Any]:
        try:
            return self.update(item)
        except ValueError:
            return self.add(item)

    def delete(self, obj_id: str) -> bool:
        data = self._read_raw()
        new_data = [d for d in data if str(d.get("id")) != str(obj_id)]
        changed = len(new_data) != len(data)
        if changed:
            self._write_raw(new_data)
        return changed
