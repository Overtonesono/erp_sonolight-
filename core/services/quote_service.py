from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

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


# ---------------- Utils dict/objet ---------------- #

def _to_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()  # pydantic v2
    try:
        return dict(obj.__dict__)
    except Exception:
        return {}

def _get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def _has_key_or_attr(obj: Any, name: str) -> bool:
    if isinstance(obj, dict):
        return name in obj
    # Pydantic v2: model_fields / v1: __fields__
    try:
        mf = getattr(obj.__class__, "model_fields", None)
        if isinstance(mf, dict) and name in mf:
            return True
    except Exception:
        pass
    return hasattr(obj, name)

def _set_safe(obj: Any, key: str, value: Any) -> None:
    """Pose la valeur seulement si le champ existe; sinon ignore."""
    if isinstance(obj, dict):
        obj[key] = value
        return
    if _has_key_or_attr(obj, key):
        try:
            setattr(obj, key, value)
        except Exception:
            pass

# ---------------- Service ---------------- #

class QuoteService:
    def __init__(self, data_dir: Optional[str | Path] = None) -> None:
        base = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data"
        base.mkdir(parents=True, exist_ok=True)
        self.repo = JsonRepository(base / "quotes.json", entity_name="quote", key="id")
        self.catalog = CatalogService()  # pour enrichir les lignes

    # ---------- Prix ---------- #

    @staticmethod
    def _price_to_cents(payload: Dict[str, Any]) -> int:
        """
        Convertit différents champs de prix vers centimes (int).
        Accepte: price_cents/price_cent/price_ttc_cent/price_ht_cent (int),
                 price_eur/price (str/float, ex "18,50").
        """
        for k in ("price_cents", "price_cent", "price_ttc_cent", "price_ht_cent"):
            if k in payload and payload[k] not in (None, ""):
                try:
                    return max(0, int(payload[k]))
                except Exception:
                    pass
        for k in ("price_eur", "price"):
            if k in payload and payload[k] not in (None, ""):
                try:
                    v = float(str(payload[k]).replace(",", "."))
                    return max(0, int(round(v * 100)))
                except Exception:
                    pass
        return 0

    # ---------- Enrichissement des lignes ---------- #

    def _find_catalog_by_ref(self, ref: str) -> Optional[Dict[str, Any]]:
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
        depuis le catalogue (product_id/service_id ou ref), sinon fallback label.
        """
        src: Optional[Dict[str, Any]] = (
            self._get_product_dict(line.get("product_id")) or
            self._get_service_dict(line.get("service_id"))
        )
        if not src and line.get("ref"):
            src = self._find_catalog_by_ref(line["ref"])

        label = line.get("label") or (src.get("label") if src else None) or (src.get("name") if src else None)
        unit = line.get("unit") if line.get("unit") is not None else (src.get("unit") if src else "")
        desc = line.get("description") or (src.get("description") if src else None) or label

        price_cents = line.get("price_cents")
        if price_cents in (None, "", 0):
            price_cents = self._price_to_cents(line)
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
        lines = qd.get("items", None)
        if lines is None:
            lines = qd.get("lines", [])
            qd["items"] = lines  # normalise sur "items"
        if not isinstance(lines, list):
            return qd
        qd["items"] = [self._enrich_line(_to_dict(x)) for x in lines]
        return qd

    # ---------- Recalcul totaux (appelé par l'UI) ---------- #

    def recalc_totals(self, quote: Any) -> Any:
        """
        Recalcule les totaux d'un devis (TTC == HT car franchise TVA).
        - Gère dict ou objet.
        - Gère lignes avec quantité 'qty' (par défaut 1), prix en euros ou centimes.
        - Met à jour:
            * pour chaque ligne: 'price_cents', 'qty', 'total_ttc_cent'
            * pour le devis: 'total_ht_cent', 'total_ttc_cent'
        Retourne l'objet mis à jour (même référence).
        """
        qd = _to_dict(quote)
        # Normaliser/enrichir lignes
        qd = self._enrich_quote_dict(qd)

        total = 0
        new_items: List[Dict[str, Any]] = []
        for line in qd.get("items", []):
            d = dict(line)
            # prix
            pc = d.get("price_cents")
            if pc in (None, "", 0):
                pc = self._price_to_cents(d)
            try:
                pc = int(pc or 0)
            except Exception:
                pc = 0
            # quantité
            qty_raw = d.get("qty", d.get("quantity", 1))
            try:
                qty = float(qty_raw if qty_raw not in (None, "") else 1)
            except Exception:
                qty = 1.0
            if qty < 0:
                qty = 0.0

            line_total = int(round(pc * qty))
            d["price_cents"] = pc
            d["qty"] = qty
            d["total_ttc_cent"] = line_total  # TTC = HT
            total += line_total
            new_items.append(d)

        # Champs calculés dans le dict normalisé
        qd["items"] = new_items
        qd["total_ht_cent"] = total
        qd["total_ttc_cent"] = total

        # ----- Réinjection dans l'objet d'origine en respectant ses champs réels -----
        # Nom du champ lignes attendu par le modèle: 'items' ou 'lines'
        lines_field_out = "items" if _has_key_or_attr(quote, "items") else "lines"
        _set_safe(quote, lines_field_out, new_items)

        # Totaux (ne pose que si le champ existe dans le modèle)
        _set_safe(quote, "total_ht_cent", total)
        _set_safe(quote, "total_ttc_cent", total)

        # Optionnel: recopie d'autres champs normalisés si le modèle les expose
        for k in ("client_id", "status", "number", "event_date"):
            if k in qd:
                _set_safe(quote, k, qd[k])

        return quote

    # ---------- CRUD ---------- #

    def list_quotes(self) -> List[Any]:
        return self.repo.list_all()

    def get_by_id(self, quote_id: str) -> Optional[Any]:
        return self.repo.find_one(lambda d: d.get("id") == quote_id)

    def add_quote(self, q: Any) -> Dict[str, Any]:
        payload = _to_dict(self.recalc_totals(q))
        return self.repo.add(payload)

    def update_quote(self, q: Any) -> Dict[str, Any]:
        payload = _to_dict(self.recalc_totals(q))
        return self.repo.upsert(payload)

    def delete_quote(self, quote_id: str) -> bool:
        return self.repo.delete(quote_id)

    # ---------- Divers ---------- #

    def list_by_client(self, client_id: str) -> List[Dict[str, Any]]:
        return self.repo.find(lambda d: d.get("client_id") == client_id)

    def load_client_map(self) -> Dict[str, Any]:
        from core.services.client_service import ClientService
        cs = ClientService()
        out = {}
        for c in cs.list_clients():
            cid = getattr(c, "id", None) or getattr(c, "id", None)
            out[cid] = c
        return out
