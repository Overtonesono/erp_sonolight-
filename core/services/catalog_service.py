from __future__ import annotations

from typing import Any, Dict, List, Optional

try:
    # pydantic v2
    from pydantic import BaseModel
except Exception:  # pragma: no cover
    class BaseModel:  # type: ignore
        def model_dump(self):
            return dict(self.__dict__)


class Service(BaseModel):  # modèle simple minimal (remplace par ton vrai modèle si déjà défini)
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    price_cents: int = 0
    active: bool = True


class Product(BaseModel):  # idem
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    price_cents: int = 0
    active: bool = True


class CatalogService:
    """
    Orchestration pour Produits & Services, au-dessus de JsonRepository.
    Attendu: repo expose add()/update()/delete()/list_all()
    """

    def __init__(self, services_repo, products_repo) -> None:
        self.services_repo = services_repo
        self.products_repo = products_repo

    # -------- Services -------- #

    def list_services(self) -> List[Dict[str, Any]]:
        return self.services_repo.list_all()

    def add_service(self, s: Service) -> Dict[str, Any]:
        # accepte BaseModel ou dict
        payload = s.model_dump() if hasattr(s, "model_dump") else dict(s)  # type: ignore
        if payload.get("price_cents") is None:
            payload["price_cents"] = 0
        return self.services_repo.add(payload)

    def update_service(self, s: Service) -> Dict[str, Any]:
        """
        Correctif PRINCIPAL: on exige un 'id' et on met à jour par ID.
        (Ancien code faisait services_repo.update(s.model_dump()) sans garantir l'id → crash)
        """
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
