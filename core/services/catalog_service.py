from __future__ import annotations
from typing import List, Optional
import os

from pydantic import ValidationError

from core.models.product import Product
from core.models.service import Service
from core.storage.repo import JsonRepository


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data"))
PRODUCTS_JSON = os.path.join(DATA_DIR, "products.json")
SERVICES_JSON = os.path.join(DATA_DIR, "services.json")


class CatalogService:
    def __init__(self, products_path: str = PRODUCTS_JSON, services_path: str = SERVICES_JSON):
        self.products_repo = JsonRepository(products_path, key="id")
        self.services_repo = JsonRepository(services_path, key="id")

    # -------- Produits --------
    def list_products(self) -> List[Product]:
        items = self.products_repo.list_all()
        out: List[Product] = []
        for d in items:
            try:
                out.append(Product(**d))
            except ValidationError:
                continue
        return out

    def add_product(self, p: Product) -> Product:
        self.products_repo.add(p.model_dump())
        return p

    def update_product(self, p: Product) -> Product:
        self.products_repo.update(p.model_dump())
        return p

    def delete_product(self, product_id: str) -> None:
        self.products_repo.delete(product_id)

    def get_product(self, product_id: str) -> Optional[Product]:
        matches = self.products_repo.find(lambda d: d.get("id") == product_id)
        if not matches:
            return None
        try:
            return Product(**matches[0])
        except ValidationError:
            return None

    # -------- Services --------
    def list_services(self) -> List[Service]:
        items = self.services_repo.list_all()
        out: List[Service] = []
        for d in items:
            try:
                out.append(Service(**d))
            except ValidationError:
                continue
        return out

    def add_service(self, s: Service) -> Service:
        self.services_repo.add(s.model_dump())
        return s

    def update_service(self, s: Service) -> Service:
        self.services_repo.update(s.model_dump())
        return s

    def delete_service(self, service_id: str) -> None:
        self.services_repo.delete(service_id)

    def get_service(self, service_id: str) -> Optional[Service]:
        matches = self.services_repo.find(lambda d: d.get("id") == service_id)
        if not matches:
            return None
        try:
            return Service(**matches[0])
        except ValidationError:
            return None
