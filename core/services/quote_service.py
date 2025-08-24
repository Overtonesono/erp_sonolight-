from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, date
from types import SimpleNamespace

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
from core.models.quote import Quote, QuoteLine  # <-- plus d'import Payment ici


# ---------------- Utils ---------------- #

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

def _parse_dt(s: Any) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    try:
        return datetime.fromisoformat(str(s))
    except Exception:
        return None

def _parse_date(s: Any) -> Optional[date]:
    if not s:
        return None
    if isinstance(s, date) and not isinstance(s, datetime):
        return s
    try:
        return datetime.fromisoformat(str(s)).date()
    except Exception:
        return None


# ---------------- Service ---------------- #

class QuoteService:
    def __init__(self, data_dir: Optional[str | Path] = None) -> None:
        base = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data"
        base.mkdir(parents=True, exist_ok=True)
        self.repo = JsonRepository(base / "quotes.json", entity_name="quote", key="id")
        self.catalog = CatalogService()

    # ---------- Enrichissement lignes ---------- #

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

        if not out.get("item_type"):
            if out.get("product_id"):
                out["item_type"] = "product"
            elif out.get("service_id"):
                out["item_type"] = "service"
            else:
                out["item_type"] = "item"
        return out

    # ---------- Hydratation Pydantic ---------- #

    def _hydrate_line(self, d: Dict[str, Any]) -> QuoteLine:
        e = self._enrich_line_dict(d)
        qty = _qty_to_float(e.get("qty", e.get("quantity", 1)))
        pc = int(e.get("price_cents") or 0)
        e["qty"] = qty
        e["total_ttc_cent"] = int(round(pc * qty))  # TTC = HT
        return QuoteLine.model_validate(e) if _HAS_PYDANTIC and hasattr(QuoteLine, "model_validate") else QuoteLine(**e)  # type: ignore

    def _hydrate_payment_obj(self, d: Dict[str, Any]) -> SimpleNamespace:
        """Retourne un petit objet avec .at/.amount_cent/.method/.invoice_id/.kind"""
        at_dt = _parse_dt(d.get("at")) or _parse_dt(d.get("date"))
        amount = int(d.get("amount_cent") or 0)
        return SimpleNamespace(
            at=at_dt,
            amount_cent=amount,
            method=d.get("method"),
            invoice_id=d.get("invoice_id"),
            kind=d.get("kind") or d.get("type") or "PAYMENT",
        )

    def _normalize_lines_key(self, qd: Dict[str, Any]) -> List[Dict[str, Any]]:
        lines = qd.get("items", None)
        if lines is None:
            lines = qd.get("lines", [])
        if not isinstance(lines, list):
            return []
        return [_to_dict(x) for x in lines]

    def _hydrate_quote(self, d: Dict[str, Any]) -> Quote:
        qd = dict(d)
        # dates
        if qd.get("event_date") and not isinstance(qd["event_date"], (date, datetime)):
            ed = _parse_date(qd["event_date"])
            if ed:
                qd["event_date"] = ed

        # lignes
        raw_lines = self._normalize_lines_key(qd)
        line_objs = [self._hydrate_line(ld) for ld in raw_lines]
        total = sum(int(getattr(ln, "total_ttc_cent", 0) or 0) for ln in line_objs)

        # paiements (objets pour l'UI)
        raw_payments = qd.get("payments", [])
        pay_objs = [self._hydrate_payment_obj(_to_dict(p)) for p in raw_payments if p is not None]

        # écrire dans la bonne clé (items vs lines) selon le modèle
        if _HAS_PYDANTIC and hasattr(Quote, "model_fields") and "items" in Quote.model_fields:  # type: ignore
            qd["items"] = [ln.model_dump() if hasattr(ln, "model_dump") else _to_dict(ln) for ln in line_objs]
        else:
            qd["lines"] = [ln.model_dump() if hasattr(ln, "model_dump") else _to_dict(ln) for ln in line_objs]

        qd["payments"] = [vars(p) for p in pay_objs]  # dicts pour hydratation Pydantic

        qd["total_ht_cent"] = total
        qd["total_ttc_cent"] = total

        q = Quote.model_validate(qd) if _HAS_PYDANTIC and hasattr(Quote, "model_validate") else Quote(**qd)  # type: ignore

        # Après hydratation, on remplace la liste par les objets pour l’UI (attributs .at etc.)
        try:
            # q.payments peut être list[...] (pydantic) → on force des objets simples
            object_payments = [self._hydrate_payment_obj(_to_dict(p)) for p in (q.payments or [])]
            setattr(q, "payments", object_payments)  # type: ignore
        except Exception:
            pass

        return q

    # ---------- Numérotation ---------- #

    def _next_quote_number(self) -> str:
        """Génère DV-YYYY-#### en incrémentant dans l'année courante."""
        year = datetime.now().year
        prefix = f"DV-{year}-"
        max_n = 0
        for d in self.repo.list_all():
            num = d.get("number") or ""
            if isinstance(num, str) and num.startswith(prefix):
                tail = num.replace(prefix, "")
                try:
                    n = int(tail)
                    if n > max_n:
                        max_n = n
                except Exception:
                    continue
        return f"{prefix}{max_n+1:04d}"

    # ---------- Recalcul (appel UI) ---------- #

    def recalc_totals(self, quote: Quote | Dict[str, Any]) -> Quote | Dict[str, Any]:
        is_dict = isinstance(quote, dict)
        qd = _to_dict(quote)

        raw_lines = self._normalize_lines_key(qd)
        line_objs = [self._hydrate_line(ld) for ld in raw_lines]
        total = sum(int(getattr(ln, "total_ttc_cent", 0) or 0) for ln in line_objs)

        # réinjection
        if is_dict:
            lines_key = "items" if "items" in quote else ("lines" if "lines" in quote else "items")
            quote[lines_key] = [ln.model_dump() if hasattr(ln, "model_dump") else _to_dict(ln) for ln in line_objs]
            quote["total_ht_cent"] = total
            quote["total_ttc_cent"] = total
            return quote

        # objet pydantic
        if hasattr(quote.__class__, "model_fields") and "items" in quote.__class__.model_fields:  # type: ignore[attr-defined]
            setattr(quote, "items", line_objs)  # type: ignore
        elif hasattr(quote, "lines"):
            setattr(quote, "lines", line_objs)  # type: ignore
        try: setattr(quote, "total_ht_cent", total)
        except Exception: pass
        try: setattr(quote, "total_ttc_cent", total)
        except Exception: pass
        return quote

    # ---------- CRUD (retours hydratés) ---------- #

    def list_quotes(self) -> List[Quote]:
        return [self._hydrate_quote(d) for d in self.repo.list_all()]

    def get_by_id(self, quote_id: str) -> Optional[Quote]:
        d = self.repo.find_one(lambda x: x.get("id") == quote_id)
        return self._hydrate_quote(d) if d else None

    def add_quote(self, q: Quote | Dict[str, Any]) -> Dict[str, Any]:
        q2 = self.recalc_totals(q)
        payload = _to_dict(q2)
        if not payload.get("number"):
            payload["number"] = self._next_quote_number()
        return self.repo.add(payload)

    def update_quote(self, q: Quote | Dict[str, Any]) -> Dict[str, Any]:
        q2 = self.recalc_totals(q)
        payload = _to_dict(q2)
        if not payload.get("number"):
            payload["number"] = self._next_quote_number()
        return self.repo.upsert(payload)

    def delete_quote(self, quote_id: str) -> bool:
        return self.repo.delete(quote_id)

    # ---------- Divers ---------- #

    def list_by_client(self, client_id: str) -> List[Quote]:
        return [self._hydrate_quote(d) for d in self.repo.find(lambda d: d.get("client_id") == client_id)]

    def load_client_map(self) -> Dict[str, Any]:
        from core.services.client_service import ClientService
        cs = ClientService()
        out = {}
        for c in cs.list_clients():
            cid = getattr(c, "id", None) or getattr(c, "id", None)
            out[cid] = c
        return out
