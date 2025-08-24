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


class CatalogService:
    """
    Orchestrateur Produits & Services.
    - Repos auto (data/services.json, data/products.json) si non fournis
    - Hydrate JSON -> objets Product/Service
    - Normalise: label <- name si absent ; unit "" ; price_cents int >= 0
    - Updates en upsert: si l'ID n'existe pas, l'entrée est créée.
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

    # ---------- Helpers ---------- #

    def _hydrate(self, d: Dict[str, Any], model: Type[T]) -> T:
        if d is None:
            raise ValueError("Object not found")
        if _HAS_PYDANTIC and hasattr(model, "model_validate"):
            obj: T = model.model_validate(d)  # type: ignore[attr-defined]
        else:
            obj = model(**d)  # type: ignore[call-arg]
        # Normalisations
        if getattr(obj, "label", None) in (None, ""):
            try:
                setattr(obj, "label", getattr(obj, "name", ""))
            except Exception:
                pass
        try:
            val = getattr(obj, "price_cents", 0)
            setattr(obj, "price_cents", int(val) if val is not None else 0)
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

    def _ensure_defaults(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = payload.get("name") or ""
        if not payload.get("label"):
            payload["label"] = name
        try:
            payload["price_cents"] = int(payload.get("price_cents") or 0)
        except Exception:
            payload["price_cents"] = 0
        if payload.get("unit") is None:
            payload["unit"] = ""
        return payload

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
        if not payload.get("id"):
            raise ValueError("update_service requires Service with 'id'")
        payload = self._ensure_defaults(payload)
        # <-- upsert au lieu de update strict
        return self.services_repo.upsert(payload)

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
        if not payload.get("id"):
            raise ValueError("update_product requires Product with 'id'")
        payload = self._ensure_defaults(payload)
        # <-- upsert au lieu de update strict
        return self.products_repo.upsert(payload)

    def delete_product(self, product_id: str) -> bool:
        return self.products_repo.delete(product_id)
