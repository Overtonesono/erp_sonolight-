from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

try:
    # pydantic v2
    from pydantic import BaseModel
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    _HAS_PYDANTIC = False

    class BaseModel:  # type: ignore
        def __init__(self, **data):
            for k, v in data.items():
                setattr(self, k, v)
        def model_dump(self) -> Dict[str, Any]:
            return dict(self.__dict__)

from core.storage.json_repo import JsonRepository


# ----------------- Modèles ----------------- #

class Service(BaseModel):
    id: Optional[str] = None
    ref: Optional[str] = None
    name: str = ""
    label: Optional[str] = None
    description: Optional[str] = None
    price_cents: int = 0
    unit: Optional[str] = ""
    active: bool = True

    @property
    def price_ttc_cent(self) -> int:  # franchise TVA: TTC == HT
        try:
            v = getattr(self, "price_cents", 0)
            return int(v) if v is not None else 0
        except Exception:
            return 0


class Product(BaseModel):
    id: Optional[str] = None
    ref: Optional[str] = None
    name: str = ""
    label: Optional[str] = None
    description: Optional[str] = None
    price_cents: int = 0
    unit: Optional[str] = ""
    active: bool = True

    @property
    def price_ttc_cent(self) -> int:  # franchise TVA: TTC == HT
        try:
            v = getattr(self, "price_cents", 0)
            return int(v) if v is not None else 0
        except Exception:
            return 0


T = TypeVar("T", bound=BaseModel)


# ----------------- Service Catalogue ----------------- #

class CatalogService:
    """
    Orchestrateur Produits & Services.
    - Repos auto (data/services.json, data/products.json) si non fournis
    - Hydrate JSON -> objets Product/Service
    - Normalise: label <- name ; unit ""; price_cents int >= 0
    - Upsert "smart" (évite duplications): tente update par id, puis ref, puis (name[,unit])
    """

    def __init__(
        self,
        services_repo: Optional[JsonRepository] = None,
        products_repo: Optional[JsonRepository] = None,
        data_dir: Optional[str | Path] = None,
    ) -> None:
        base = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data"
        base.mkdir(parents=True, exist_ok=True)

        self.services_repo = services_repo or JsonRepository(
            base / "services.json", entity_name="service", key="id"
        )
        self.products_repo = products_repo or JsonRepository(
            base / "products.json", entity_name="product", key="id"
        )

    # ---------- Helpers (prix & normalisation) ---------- #

    @staticmethod
    def _parse_price_to_cents(payload: Dict[str, Any]) -> int:
        """
        Accepte:
          - price_cents (int)
          - price_cent (int)
          - price_ttc_cent / price_ht_cent (int)
          - price / price_eur (str/float, ex "18,50" → 1850)
        Retourne un int >= 0
        """
        keys_int = ["price_cents", "price_cent", "price_ttc_cent", "price_ht_cent"]
        for k in keys_int:
            if k in payload and payload[k] is not None:
                try:
                    return max(0, int(payload[k]))
                except Exception:
                    pass

        for k in ["price", "price_eur"]:
            if k in payload and payload[k] is not None:
                v = str(payload[k]).strip()
                if v == "":
                    continue
                # remplace virgule FR par point
                v = v.replace(",", ".")
                try:
                    euros = float(v)
                    return max(0, int(round(euros * 100)))
                except Exception:
                    continue

        return 0

    def _ensure_defaults(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # label <- name si absent
        name = payload.get("name") or ""
        if not payload.get("label"):
            payload["label"] = name
        # unit par défaut ""
        if payload.get("unit") is None:
            payload["unit"] = ""
        # price_cents robuste
        payload["price_cents"] = self._parse_price_to_cents(payload)
        return payload

    # ---------- Helpers (hydratation objets) ---------- #

    def _hydrate(self, d: Dict[str, Any], model: Type[T]) -> T:
        if d is None:
            raise ValueError("Object not found")
        if _HAS_PYDANTIC and hasattr(model, "model_validate"):
            obj: T = model.model_validate(d)  # type: ignore[attr-defined]
        else:
            obj = model(**d)  # type: ignore[call-arg]

        # Normalisations lecture
        if getattr(obj, "label", None) in (None, ""):
            try:
                setattr(obj, "label", getattr(obj, "name", ""))
            except Exception:
                pass
        # Harmonise price_cents depuis éventuelles clés héritées
        try:
            pc = getattr(obj, "price_cents", None)
            if pc in (None, "", 0):
                # si JSON contient d'autres clés historiques
                raw = d
                setattr(obj, "price_cents", self._parse_price_to_cents(raw))
            else:
                setattr(obj, "price_cents", int(pc))
        except Exception:
            setattr(obj, "price_cents", 0)

        if getattr(obj, "unit", None) is None:
            try:
                setattr(obj, "unit", "")
            except Exception:
                pass
        return obj

    def _hydrate_list(self, rows: List[Dict[str, Any]], model: Type[T]) -> List[T]:
        return [self._hydrate(d, model) for d in rows]

    # ---------- Helpers (upsert smart pour éviter les doublons) ---------- #

    @staticmethod
    def _match_row(row: Dict[str, Any], probe: Dict[str, Any]) -> bool:
        """
        Priorité: id -> ref -> (name, unit) -> name
        """
        if probe.get("id") and str(row.get("id")) == str(probe["id"]):
            return True
        if probe.get("ref") and row.get("ref") and str(row["ref"]).strip() == str(probe["ref"]).strip():
            return True
        name = (probe.get("name") or "").strip()
        if name:
            unit = (probe.get("unit") or "").strip()
            if unit:
                return (row.get("name") or "").strip() == name and (row.get("unit") or "").strip() == unit
            # fallback name seul si unique plus bas
        return False

    @staticmethod
    def _find_unique_by_name(rows: List[Dict[str, Any]], name: str) -> Optional[int]:
        idxs = [i for i, r in enumerate(rows) if (r.get("name") or "").strip() == name.strip()]
        if len(idxs) == 1:
            return idxs[0]
        return None

    def _smart_upsert(self, repo: JsonRepository, payload: Dict[str, Any]) -> Dict[str, Any]:
        rows = repo.list_all()

        # 1) match strict id/ref/(name,unit)
        for i, r in enumerate(rows):
            if self._match_row(r, payload):
                merged = {**r, **payload}
                rows[i] = merged
                # écriture atomique via repo._write_raw (API interne)
                repo._write_raw(rows)  # type: ignore[attr-defined]
                return merged

        # 2) si name seul correspond à UN unique enregistrement -> update
        name = (payload.get("name") or "").strip()
        if name:
            idx = self._find_unique_by_name(rows, name)
            if idx is not None:
                merged = {**rows[idx], **payload}
                rows[idx] = merged
                repo._write_raw(rows)  # type: ignore[attr-defined]
                return merged

        # 3) sinon -> add (en conservant l'id si déjà fourni)
        return repo.add(payload)

    # ---------- Services ---------- #

    def list_services(self) -> List[Service]:
        rows = self.services_repo.list_all()
        return self._hydrate_list(rows, Service)

    def get_service(self, service_id: str) -> Service:
        row = self.services_repo.get_by_id(service_id)
        return self._hydrate(row, Service)

    def add_service(self, s: Service) -> Dict[str, Any]:
        payload = s.model_dump() if hasattr(s, "model_dump") else dict(s)  # type: ignore
        payload = self._ensure_defaults(payload)
        return self.services_repo.add(payload)

    def update_service(self, s: Service) -> Dict[str, Any]:
        payload = s.model_dump() if hasattr(s, "model_dump") else dict(s)  # type: ignore
        if not payload.get("id") and not payload.get("ref") and not payload.get("name"):
            raise ValueError("update_service requires at least one key (id/ref/name)")
        payload = self._ensure_defaults(payload)
        return self._smart_upsert(self.services_repo, payload)

    def delete_service(self, service_id: str) -> bool:
        return self.services_repo.delete(service_id)

    # ---------- Produits ---------- #

    def list_products(self) -> List[Product]:
        rows = self.products_repo.list_all()
        return self._hydrate_list(rows, Product)

    def get_product(self, product_id: str) -> Product:
        row = self.products_repo.get_by_id(product_id)
        return self._hydrate(row, Product)

    def add_product(self, p: Product) -> Dict[str, Any]:
        payload = p.model_dump() if hasattr(p, "model_dump") else dict(p)  # type: ignore
        payload = self._ensure_defaults(payload)
        return self.products_repo.add(payload)

    def update_product(self, p: Product) -> Dict[str, Any]:
        payload = p.model_dump() if hasattr(p, "model_dump") else dict(p)  # type: ignore
        if not payload.get("id") and not payload.get("ref") and not payload.get("name"):
            raise ValueError("update_product requires at least one key (id/ref/name)")
        payload = self._ensure_defaults(payload)
        return self._smart_upsert(self.products_repo, payload)

    def delete_product(self, product_id: str) -> bool:
        return self.products_repo.delete(product_id)
