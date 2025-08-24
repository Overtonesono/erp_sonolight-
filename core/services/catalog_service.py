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
    ref: Optional[str] = None        # <— pour l’UI (p.ref)
    name: str = ""
    description: Optional[str] = None
    price_cents: int = 0
    active: bool = True


class Product(BaseModel):
    id: Optional[str] = None
    ref: Optional[str] = None        # <— pour l’UI (p.ref)
    name: str = ""
    description: Optional[str] = None
    price_cents: int = 0
    active: bool = True


T = TypeVar("T", bound=BaseModel)


class CatalogService:
    """
    Orchestrateur Produits & Services.
    - Si aucun repo n'est fourni, crée automatiquement data/services.json et data/products.json
    - Hydrate les enregistrements JSON en objets Product/Service (l’UI peut faire p.ref, p.name, etc.)
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
                # pydantic v2
                obj = model.model_validate(d)  # type: ignore[attr-defined]
            else:
                obj = model(**d)  # type: ignore[call-arg]
            items.append(obj)
        return items

    # ---------- Services ---------- #

    def list_services(self) -> List[Service]:
        rows = self.services_repo.list_all()
        return self._hydrate_list(rows, Service)

    def add_service(self, s: Service) -> Dict[str, Any]:
        payload = s.model_dump() if hasattr(s, "model_dump") else dict(s)  # type: ignore
        if payload.get("price_cents") is None:
            payload["price_cents"] = 0
        return self.services_repo.add(payload)

    def update_service(self, s: Service) -> Dict[str, Any]:
        payload = s.model_dump() if hasattr(s, "model_dump") else dict(s)  # type: ignore
        if not payload.get("id"):
            raise ValueError("update_service requires Service with 'id'")
        return self.services_repo.update(payload)

    def delete_service(self, service_id: str) -> bool:
        return self.services_repo.delete(service_id)

    # ---------- Produits ---------- #

    def list_products(self) -> List[Product]:
        rows = self.products_repo.list_all()
        return self._hydrate_list(rows, Product)

    def add_product(self, p: Product) -> Dict[str, Any]:
        payload = p.model_dump() if hasattr(p, "model_dump") else dict(p)  # type: ignore
        if payload.get("price_cents") is None:
            payload["price_cents"] = 0
        return self.products_repo.add(payload)

    def update_product(self, p: Product) -> Dict[str, Any]:
        payload = p.model_dump() if hasattr(p, "model_dump") else dict(p)  # type: ignore
        if not payload.get("id"):
            raise ValueError("update_product requires Product with 'id'")
        return self.products_repo.update(payload)

    def delete_product(self, product_id: str) -> bool:
        return self.products_repo.delete(product_id)
