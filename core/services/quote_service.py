from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

try:
    from pydantic import BaseModel
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    _HAS_PYDANTIC = False
    class BaseModel:  # type: ignore
        def model_dump(self) -> Dict[str, Any]:
            return dict(self.__dict__)

from core.storage.json_repo import JsonRepository
from core.services.catalog_service import CatalogService


def _to_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # pydantic v2
    try:
        return dict(obj.__dict__)
    except Exception:
        return {}


class QuoteService:
    def __init__(self, data_dir: Optional[str | Path] = None) -> None:
        base = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data"
        base.mkdir(parents=True, exist_ok=True)
        self.repo = JsonRepository(base / "quotes.json", entity_name="quote", key="id")
        self.catalog = CatalogService()  # pour enrichir les lignes

    # ------------- Helpers ------------- #

    def _find_catalog_by_ref(self, ref: str) -> Optional[Dict[str, Any]]:
        # Cherche d'abord produit, puis service
        for p in self.catalog.list_products():
            if (p.ref or "").strip() == (ref or "").strip():
                return p.model_dump() if hasattr(p, "model_dump") else dict(p.__dict__)
        for s in self.catalog.list_services():
            if (s.ref or "").strip() == (ref or "").strip():
                return s.model_dump() if hasattr(s, "model_dump") else dict(s.__dict__)
        return None

    def _get_product_dict(self, pid: Optional[str]) -> Optional[Dict[str, Any]]:
        if not pid:
            return None
        try:
            p = self.catalog.get_product(pid)
            return p.model_dump() if hasattr(p, "model_dump") else dict(p.__dict__)
        except Exception:
            return None

    def _get_service_dict(self, sid: Optional[str]) -> Optional[Dict[str, Any]]:
        if not sid:
            return None
        try:
            s = self.catalog.get_service(sid)
            return s.model_dump() if hasattr(s, "model_dump") else dict(s.__dict__)
        except Exception:
            return None

    def _enrich_line(self, line: Dict[str, Any]) -> Dict[str, Any]:
        """
        Complète la ligne: description, label, unit, price_cents si manquants
        à partir du catalogue (product_id/service_id ou ref), sinon fallback label.
        """
        src: Optional[Dict[str, Any]] = None

        # 1) par id
        src = self._get_product_dict(line.get("product_id")) or self._get_service_dict(line.get("service_id"))

        # 2) par ref si pas trouvé
        if not src and line.get("ref"):
            src = self._find_catalog_by_ref(line["ref"])

        # Fallbacks
        label = line.get("label") or (src.get("label") if src else None) or (src.get("name") if src else None)
        unit = line.get("unit") if line.get("unit") is not None else (src.get("unit") if src else "")
        desc = line.get("description") or (src.get("description") if src else None) or label
        # Prix: laisse ce qui vient de l'éditeur si présent; sinon reprend du catalogue
        price_cents = line.get("price_cents")
        if price_cents in (None, "", 0) and src:
            price_cents = src.get("price_cents") or 0
        try:
            price_cents = int(price_cents or 0)
        except Exception:
            price_cents = 0

        out = dict(line)
        out.setdefault("ref", src.get("ref") if (src and not out.get("ref")) else out.get("ref"))
        out["label"] = label or ""
        out["unit"] = unit or ""
        out["description"] = desc or ""
        out["price_cents"] = price_cents
        return out

    def _enrich_quote_dict(self, qd: Dict[str, Any]) -> Dict[str, Any]:
        # Les lignes peuvent s'appeler "items" ou "lines" suivant versions
        lines = qd.get("items", None)
        if lines is None:
            lines = qd.get("lines", [])
            qd["items"] = lines  # normalise sur "items"
        if not isinstance(lines, list):
            return qd
        qd["items"] = [self._enrich_line(_to_dict(x)) for x in lines]
        return qd

    # ------------- CRUD ------------- #

    def list_quotes(self) -> List[Any]:
        return self.repo.list_all()

    def get_by_id(self, quote_id: str) -> Optional[Any]:
        m = self.repo.find_one(lambda d: d.get("id") == quote_id)
        return m

    def add_quote(self, q: Any) -> Dict[str, Any]:
        payload = _to_dict(q)
        payload = self._enrich_quote_dict(payload)
        return self.repo.add(payload)

    def update_quote(self, q: Any) -> Dict[str, Any]:
        payload = _to_dict(q)
        payload = self._enrich_quote_dict(payload)
        # upsert pour robustesse (si id non trouvé)
        return self.repo.upsert(payload)

    def delete_quote(self, quote_id: str) -> bool:
        return self.repo.delete(quote_id)

    # ------------- Export (si utilisé ici) ------------- #

    def list_by_client(self, client_id: str) -> List[Dict[str, Any]]:
        return self.repo.find(lambda d: d.get("client_id") == client_id)

    def load_client_map(self) -> Dict[str, Any]:
        # compat méthode existante dans MainWindow
        from core.services.client_service import ClientService
        cs = ClientService()
        out = {}
        for c in cs.list_clients():
            cid = getattr(c, "id", None) or getattr(c, "id", None)
            out[cid] = c
        return out
