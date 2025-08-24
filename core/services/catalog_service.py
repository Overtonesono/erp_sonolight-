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

    # Franchise TVA: TTC == HT
    @property
    def price_ttc_cent(self) -> int:
        return int(self.price_cents or 0)

    @property
    def price_eur(self) -> float:
        """Prix exprimé en euros pour édition/affichage."""
        return round((self.price_cents or 0) / 100.0, 2)


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
    def price_ttc_cent(self) -> int:
        return int(self.price_cents or 0)

    @property
    def price_eur(self) -> float:
        return round((self.price_cents or 0) / 100.0, 2)


T = TypeVar("T", bound=BaseModel)


# ----------------- Service Catalogue ----------------- #

class CatalogService:
    """
    Orchestrateur Produits & Services.
    - Stockage interne en centimes
    - Exposition d'une propriété `price_eur` pour l'édition en euros
    - Upsert "smart" pour éviter duplications
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

    def _parse_price_cents(self, payload: Dict[str, Any]) -> int:
        """Convertit price_eur → price_cents si présent, sinon conserve centimes."""
        if "price_eur" in payload and payload["price_eur"] not in (None, ""):
            try:
                val = float(str(payload["price_eur"]).replace(",", "."))
                return int(round(val * 100))
            except Exception:
                return 0
        return int(payload.get("price_cents") or 0)

    def _ensure_defaults(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = payload.get("name") or ""
        if not payload.get("label"):
            payload["label"] = name
        if payload.get("unit") is None:
            payload["unit"] = ""
        payload["price_cents"] = self._parse_price_cents(payload)
        return payload

    def _hydrate(self, d: Dict[str, Any], model: Type[T]) -> T:
        if d is None:
            raise ValueError("Object not found")
        if _HAS_PYDANTIC and hasattr(model, "model_validate"):
            obj: T = model.model_validate(d)  # type: ignore[attr-defined]
        else:
            obj = model(**d)  # type: ignore[call-arg]
        return obj

    def _hydrate_list(self, rows: List[Dict[str, Any]], model: Type[T]) -> List[T]:
        return [self._hydrate(d, model) for d in rows]

    def _smart_upsert(self, repo: JsonRepository, payload: Dict[str, Any]) -> Dict[str, Any]:
        rows = repo.list_all()

        # id
        if payload.get("id"):
            for i, r in enumerate(rows):
                if str(r.get("id")) == str(payload["id"]):
                    merged = {**r, **payload}
                    rows[i] = merged
                    repo._write_raw(rows)  # type: ignore
                    return merged

        # ref
        if payload.get("ref"):
            for i, r in enumerate(rows):
                if r.get("ref") and str(r["ref"]) == str(payload["ref"]):
                    merged = {**r, **payload}
                    rows[i] = merged
                    repo._write_raw(rows)  # type: ignore
                    return merged

        # name + unit
        if payload.get("name"):
            for i, r in enumerate(rows):
                if (r.get("name") == payload["name"]) and (r.get("unit") == payload.get("unit", "")):
                    merged = {**r, **payload}
                    rows[i] = merged
                    repo._write_raw(rows)  # type: ignore
                    return merged

        # sinon add
        return repo.add(payload)

    # ---------- Services ---------- #

    def list_services(self) -> List[Service]:
        return self._hydrate_list(self.services_repo.list_all(), Service)

    def get_service(self, service_id: str) -> Service:
        return self._hydrate(self.services_repo.get_by_id(service_id), Service)

    def add_service(self, s: Service) -> Dict[str, Any]:
        return self.services_repo.add(self._ensure_defaults(s.model_dump()))

    def update_service(self, s: Service) -> Dict[str, Any]:
        payload = self._ensure_defaults(s.model_dump())
        return self._smart_upsert(self.services_repo, payload)

    def delete_service(self, service_id: str) -> bool:
        return self.services_repo.delete(service_id)

    # ---------- Produits ---------- #

    def list_products(self) -> List[Product]:
        return self._hydrate_list(self.products_repo.list_all(), Product)

    def get_product(self, product_id: str) -> Product:
        return self._hydrate(self.products_repo.get_by_id(product_id), Product)

    def add_product(self, p: Product) -> Dict[str, Any]:
        return self.products_repo.add(self._ensure_defaults(p.model_dump()))

    def update_product(self, p: Product) -> Dict[str, Any]:
        payload = self._ensure_defaults(p.model_dump())
        return self._smart_upsert(self.products_repo, payload)

    def delete_product(self, product_id: str) -> bool:
        return self.products_repo.delete(product_id)
