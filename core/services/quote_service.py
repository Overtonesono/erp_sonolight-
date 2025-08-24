from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Type

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
# Modèles du projet
from core.models.quote import Quote, QuoteLine  # importants pour hydrater correctement


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

def _price_to_cents(payload: Dict[str, Any]) -> int:
    """Accepte price_cents/price_cent/price_ttc_cent/price_ht_cent (int) ou price/price_eur ('18,50')."""
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

def _qty_to_float(v: Any) -> float:
    try:
        if v in (None, ""):
            return 1.0
        return max(0.0, float(v))
    except Exception:
        return 1.0


# ---------------- Service ---------------- #

class QuoteService:
    def __init__(self, data_dir: Optional[str | Path] = None) -> None:
        base = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data"
        base.mkdir(parents=True, exist_ok=True)
        self.repo = JsonRepository(base / "quotes.json", entity_name="quote", key="id")
        self.catalog = CatalogService()  # pour enrichir les lignes

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

    def _enrich_line_dict(self, line: Dict[str, Any]) -> Dict[str, Any]:
        """
        Complète la ligne dict: description, label, unit, price_cents si manquants
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
        desc = line.get("description") or (src.get("description") if src else None) or (label or "")

        price_cents = line.get("price_cents")
        if price_cents in (None, "", 0):
            price_cents = _price_to_cents(line)
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

        # Déduire item_type si pas fourni
        if not out.get("item_type"):
            if out.get("product_id"):
                out["item_type"] = "product"
            elif out.get("service_id"):
                out["item_type"] = "service"
            else:
                out["item_type"] = "item"
        return out

    # ---------- Hydratation objets Pydantic ---------- #

    def _hydrate_line(self, d: Dict[str, Any]) -> QuoteLine:
        """Dict → QuoteLine (Pydantic)."""
        enriched = self._enrich_line_dict(d)
        # qty / totals
        qty = _qty_to_float(enriched.get("qty", enriched.get("quantity", 1)))
        price_cents = int(enriched.get("price_cents") or 0)
        enriched["qty"] = qty
        enriched["total_ttc_cent"] = int(round(price_cents * qty))  # TTC = HT

        if _HAS_PYDANTIC and hasattr(QuoteLine, "model_validate"):
            return QuoteLine.model_validate(enriched)  # type: ignore[attr-defined]
        return QuoteLine(**enriched)  # type: ignore[call-arg]

    def _normalize_lines_key(self, qd: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retourne la liste dict des lignes en lisant 'items' ou 'lines'."""
        lines = qd.get("items", None)
        if lines is None:
            lines = qd.get("lines", [])
        if not isinstance(lines, list):
            return []
        # Ensure dicts
        out: List[Dict[str, Any]] = []
        for x in lines:
            out.append(_to_dict(x))
        return out

    def _hydrate_quote(self, d: Dict[str, Any]) -> Quote:
        """Dict → Quote (Pydantic) avec lignes hydratées en QuoteLine et totaux recalculés."""
        qd = dict(d)
        raw_lines = self._normalize_lines_key(qd)
        line_objs = [self._hydrate_line(ld) for ld in raw_lines]
        total = sum(int(getattr(ln, "total_ttc_cent", 0) or 0) for ln in line_objs)
        # Ecrire sous le bon nom de champ selon le modèle (items vs lines)
        if _HAS_PYDANTIC and hasattr(Quote, "model_fields") and "items" in Quote.model_fields:  # type: ignore
            qd["items"] = [ln.model_dump() if hasattr(ln, "model_dump") else _to_dict(ln) for ln in line_objs]
        else:
            qd["lines"] = [ln.model_dump() if hasattr(ln, "model_dump") else _to_dict(ln) for ln in line_objs]
        qd["total_ht_cent"] = total
        qd["total_ttc_cent"] = total

        if _HAS_PYDANTIC and hasattr(Quote, "model_validate"):
            return Quote.model_validate(qd)  # type: ignore[attr-defined]
        return Quote(**qd)  # type: ignore[call-arg]

    # ---------- Recalcul totaux (appelé par l'UI) ---------- #

    def recalc_totals(self, quote: Quote | Dict[str, Any]) -> Quote | Dict[str, Any]:
        """
        Recalcule dans l'objet reçu (Pydantic ou dict).
        - Reconstruit les QuoteLine, met à jour qty/price/total.
        - Met à jour total_ht_cent/total_ttc_cent.
        - Conserve le type d’objet en sortie.
        """
        is_dict = isinstance(quote, dict)
        qd = _to_dict(quote)

        # (Ré)hydratation des lignes en objets pour calcul
        raw_lines = self._normalize_lines_key(qd)
        line_objs = [self._hydrate_line(ld) for ld in raw_lines]

        total = sum(int(getattr(ln, "total_ttc_cent", 0) or 0) for ln in line_objs)

        # Réinjection selon type d'entrée
        if is_dict:
            # dict : garder la même clé de lignes que l’entrée
            lines_key = "items" if "items" in quote else ("lines" if "lines" in quote else "items")
            quote[lines_key] = [ln.model_dump() if hasattr(ln, "model_dump") else _to_dict(ln) for ln in line_objs]
            quote["total_ht_cent"] = total
            quote["total_ttc_cent"] = total
            return quote

        # Objet Pydantic : écrire dans le champ présent (items ou lines)
        if hasattr(quote.__class__, "model_fields") and "items" in quote.__class__.model_fields:  # type: ignore[attr-defined]
            setattr(quote, "items", line_objs)  # Pydantic sait caster QuoteLine -> bon type
        elif hasattr(quote, "lines"):
            setattr(quote, "lines", line_objs)  # type: ignore
        # Totaux
        try:
            setattr(quote, "total_ht_cent", total)
        except Exception:
            pass
        try:
            setattr(quote, "total_ttc_cent", total)
        except Exception:
            pass

        return quote

    # ---------- CRUD (retours hydratés pour l'UI) ---------- #

    def list_quotes(self) -> List[Quote]:
        rows = self.repo.list_all()
        return [self._hydrate_quote(d) for d in rows]

    def get_by_id(self, quote_id: str) -> Optional[Quote]:
        d = self.repo.find_one(lambda x: x.get("id") == quote_id)
        return self._hydrate_quote(d) if d else None

    def add_quote(self, q: Quote | Dict[str, Any]) -> Dict[str, Any]:
        # Calculs + enrichissement
        q2 = self.recalc_totals(q)
        payload = _to_dict(q2)
        return self.repo.add(payload)

    def update_quote(self, q: Quote | Dict[str, Any]) -> Dict[str, Any]:
        q2 = self.recalc_totals(q)
        payload = _to_dict(q2)
        return self.repo.upsert(payload)

    def delete_quote(self, quote_id: str) -> bool:
        return self.repo.delete(quote_id)

    # ---------- Divers ---------- #

    def list_by_client(self, client_id: str) -> List[Quote]:
        rows = self.repo.find(lambda d: d.get("client_id") == client_id)
        return [self._hydrate_quote(d) for d in rows]

    def load_client_map(self) -> Dict[str, Any]:
        from core.services.client_service import ClientService
        cs = ClientService()
        out = {}
        for c in cs.list_clients():
            cid = getattr(c, "id", None) or getattr(c, "id", None)
            out[cid] = c
        return out
