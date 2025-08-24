from __future__ import annotations

import glob
import json
import shutil
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, Generic, Iterable, List, Mapping, Optional, TypeVar, Union
from uuid import uuid4

try:
    from pydantic import BaseModel
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    _HAS_PYDANTIC = False
    class BaseModel:  # type: ignore
        def model_dump(self) -> Dict[str, Any]:
            return dict(self.__dict__)


T = TypeVar("T", bound=Union[BaseModel, Mapping[str, Any]])


def _json_default(o: Any) -> Any:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return str(o)


class JsonRepository(Generic[T]):
    """
    Repo JSON générique avec clé primaire configurable.
    - Rotation de backups (backup_enabled, backup_keep)
    - N'écrit pas si le contenu ne change pas (réduction du bruit et des .bak)
    """

    def __init__(
        self,
        filepath: Union[str, Path],
        entity_name: str = "entity",
        key: str = "id",
        *,
        backup_enabled: bool = True,
        backup_keep: int = 5,
    ) -> None:
        self.filepath = Path(filepath)
        self.entity_name = entity_name
        self.key = key
        self._lock = threading.Lock()
        self.backup_enabled = backup_enabled
        self.backup_keep = max(0, int(backup_keep))

        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        if not self.filepath.exists():
            self._write_raw([])

    # ---------------- I/O bas niveau ---------------- #

    def _read_raw(self) -> List[Dict[str, Any]]:
        try:
            with self.filepath.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
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

    def _rotate_backups(self) -> None:
        if not self.backup_enabled or self.backup_keep <= 0:
            return
        pattern = str(self.filepath.with_suffix(".*.bak.json"))
        files = sorted(glob.glob(pattern))
        # garde les plus récents
        if len(files) > self.backup_keep:
            for old in files[: len(files) - self.backup_keep]:
                try:
                    Path(old).unlink(missing_ok=True)
                except Exception:
                    pass

    def _write_raw(self, data: Iterable[Mapping[str, Any]]) -> None:
        with self._lock:
            new_dump = json.dumps(list(data), ensure_ascii=False, indent=2, default=_json_default)

            # si contenu identique → ne rien faire
            if self.filepath.exists():
                try:
                    cur = self.filepath.read_text(encoding="utf-8")
                    if cur == new_dump:
                        return
                except Exception:
                    pass

            # backup
            if self.backup_enabled and self.filepath.exists():
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                backup = self.filepath.with_suffix(f".{ts}.bak.json")
                try:
                    shutil.copy2(self.filepath, backup)
                except Exception:
                    pass
                self._rotate_backups()

            # write
            with self.filepath.open("w", encoding="utf-8") as f:
                f.write(new_dump)

    # ---------------- Helpers ---------------- #

    @staticmethod
    def _to_dict(item: T) -> Dict[str, Any]:
        if _HAS_PYDANTIC and isinstance(item, BaseModel):
            return item.model_dump()
        if hasattr(item, "model_dump"):
            return item.model_dump()
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
        rows = self._read_raw()
        out: List[Dict[str, Any]] = []
        for r in rows:
            try:
                if predicate(r):
                    out.append(r)
            except Exception:
                continue
        return out

    def find_one(self, predicate: Callable[[Dict[str, Any]], bool]) -> Optional[Dict[str, Any]]:
        rows = self._read_raw()
        for r in rows:
            try:
                if predicate(r):
                    return r
            except Exception:
                continue
        return None
