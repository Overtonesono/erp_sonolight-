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
    label: Optional[str] = None     # <-- attendu par l'UI
    description: Optional[str] = None
    price_cents: int = 0
    active: bool = True


class Product(BaseModel):
    id: Optional[str] = None
    ref: Optional[str] = None
    name: str = ""
    label: Optional[str] = None     # <-- attendu par l'UI
    description: Optional[str] = None
    price_cents: int = 0
    active: bool = True


T = TypeVar("T", bound=BaseModel)


class CatalogService:
    """
    Orchestrateur Produits & Services.
    - Si aucun repo n'est fourni, crée automatiquement data/services.json et data/products.json
    - Hydrate JSON -> objets Product/Service (avec champs 'ref', 'label', etc.)
    - Normalise: si 'label' absent, utilise 'name'
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

    def _hydrate_list(self, rows: List[Dict[str, Any]], model: Type[T]) -> List[T]:
        items: List[T] = []
        for d in rows:
            if _HAS_PYDANTIC and hasattr(model, "model_validate"):
                obj: T = model.model_validate(d)  # type: ignore[attr-defined]
            else:
                obj = model(**d)  # type: ignore[call-arg]
            # Normalisation: label fallback sur name
            if getattr(obj, "label", None) in (None, ""):
                try:
                    setattr(obj, "label", getattr(obj, "name", ""))  # mutation autorisée par défaut
                except Exception:
                    pass
            items.append(obj)
        return items

    def _ensure_defaults(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # S'assure que label existe (fallback name), price_cents non nul
        name = payload.get("name") or ""
        if not payload.get("label"):
            payload["label"] = name
        if payload.get("price_cents") is None:
            payload["price_cents"] = 0
        return payload

    # ---------- Services ---------- #

    def list_services(self) -> List[Service]:
        rows = self.services_repo.list_all()
        return self._hydrate_list(rows, Service)

    def add_service(self, s: Service) -> Dict[str, Any]:
        payload = s.model_dump() if hasattr(s, "model_dump") else dict(s)  # type: ignore
        payload = self._ensure_defaults(payload)
        return self.services_repo.add(payload)

    def update_service(self, s: Service) -> Dict[str, Any]:
        payload = s.model_dump() if hasattr(s, "model_dump") else dict(s)  # type: ignore
        if not payload.get("id"):
            raise ValueError("update_service requires Service with 'id'")
        payload = self._ensure_defaults(payload)
        return self.services_repo.update(payload)

    def delete_service(self, service_id: str) -> bool:
        return self.services_repo.delete(service_id)

    # ---------- Produits ---------- #

    def list_products(self) -> List[Product]:
        rows = self.products_repo.list_all()
        return self._hydrate_list(rows, Product)

    def add_product(self, p: Product) -> Dict[str, Any]:
        payload = p.model_dump() if hasattr(p, "model_dump") else dict(p)  # type: ignore
        payload = self._ensure_defaults(payload)
        return self.products_repo.add(payload)

    def update_product(self, p: Product) -> Dict[str, Any]:
        payload = p.model_dump() if hasattr(p, "model_dump") else dict(p)  # type: ignore
        if not payload.get("id"):
            raise ValueError("update_product requires Product with 'id'")
        payload = self._ensure_defaults(payload)
        return self.products_repo.update(payload)

    def delete_product(self, product_id: str) -> bool:
        return self.products_repo.delete(product_id)
