from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    # pydantic v2
    from pydantic import BaseModel
except Exception:  # pragma: no cover
    class BaseModel:  # type: ignore
        def model_dump(self):
            return dict(self.__dict__)

# Repo JSON générique
from core.storage.json_repo import JsonRepository


class Service(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    price_cents: int = 0
    active: bool = True


class Product(BaseModel):
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    price_cents: int = 0
    active: bool = True


class CatalogService:
    """
    Orchestrateur Produits & Services.
    Si aucun repo n'est fourni, crée automatiquement:
      data/services.json et data/products.json
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

    # -------- Services -------- #

    def list_services(self) -> List[Dict[str, Any]]:
        return self.services_repo.list_all()

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

    # -------- Produits -------- #

    def list_products(self) -> List[Dict[str, Any]]:
        return self.products_repo.list_all()

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
