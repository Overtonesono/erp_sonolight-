from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, date
from types import SimpleNamespace

try:
    from pydantic import BaseModel  # noqa: F401
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    _HAS_PYDANTIC = False
    class BaseModel:  # type: ignore
        def model_dump(self) -> Dict[str, Any]:
            return dict(self.__dict__)

from core.storage.json_repo import JsonRepository
from core.services.catalog_service import CatalogService
from core.models.quote import Quote, QuoteLine


# ---------- Helpers ---------- #

def _cent_to_str(c: int) -> str:
    try:
        return f"{(int(c) if c is not None else 0)/100:.2f} €"
    except Exception:
        return "0.00 €"

def _escape_html(s: Any) -> str:
    from html import escape
    return escape("" if s is None else str(s))

def _find_wkhtmltopdf_exe() -> Optional[str]:
    import os, shutil
    env_path = os.environ.get("WKHTMLTOPDF_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    p = shutil.which("wkhtmltopdf")
    if p:
        return p
    for c in [
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files\wkhtmltopdf\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\wkhtmltopdf.exe",
    ]:
        if os.path.isfile(c):
            return c
    return None

def _to_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    try:
        return dict(obj.__dict__)
    except Exception:
        return {}

def _clean_decimal(val: Any):
    from decimal import Decimal, InvalidOperation
    import re
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        try:
            return Decimal(str(val))
        except Exception:
            return None
    s = str(val)
    s = re.sub(r"[^0-9,.\-]", "", s)
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None

def _qty_to_float(v: Any) -> float:
    try:
        if v in (None, ""):
            return 1.0
        return max(0.0, float(v))
    except Exception:
        return 1.0


# ---------- Prix (robuste) ---------- #

def _price_to_cents(payload: Dict[str, Any]) -> int:
    """
    Conversion "souple" -> centimes.
    Préfère les *_cent(s) puis *_eur, sinon heuristique sur 'price'/'unit_price'.
    """
    # 1) clés en centimes (prioritaires)
    for k in ("price_cents", "price_cent", "unit_price_cent", "unit_price_cents", "price_ttc_cent", "price_ht_cent"):
        v = payload.get(k)
        if v not in (None, ""):
            try:
                return max(0, int(v))
            except Exception:
                pass

    # 2) clés en euros
    for k in ("price_eur", "unit_price_eur", "ttc_eur"):
        v = payload.get(k)
        d = _clean_decimal(v)
        if d is not None:
            return max(0, int(d * 100))

    # 3) heuristique sur 'unit_price' / 'price'
    for k in ("unit_price", "price"):
        v = payload.get(k)
        d = _clean_decimal(v)
        if d is None:
            continue
        # Si valeur entière >= 10000 -> on suppose déjà des centimes
        try:
            if d == int(d) and int(d) >= 10000:
                return max(0, int(d))
        except Exception:
            pass
        return max(0, int(d * 100))

    # 4) pas trouvable
    return 0

def _extract_unit_price_cents(line_like: Dict[str, Any]) -> int:
    """Encore plus strict: tente toutes les variantes + dérive depuis total/qty si besoin."""
    d = dict(line_like or {})
    # centimes directs
    for k in ("price_cents", "price_cent", "unit_price_cent", "unit_price_cents"):
        v = d.get(k)
        if v not in (None, "", 0):
            try:
                return int(v)
            except Exception:
                pass
    # euros connus
    for k in ("unit_price_eur", "price_eur"):
        v = d.get(k)
        dec = _clean_decimal(v)
        if dec is not None:
            return int(max(0, dec * 100))
    # heuristique price / unit_price
    for k in ("unit_price", "price"):
        v = d.get(k)
        dec = _clean_decimal(v)
        if dec is None:
            continue
        try:
            if dec == int(dec) and int(dec) >= 10000:
                return int(dec)  # déjà des centimes
        except Exception:
            pass
        return int(max(0, dec * 100))
    # dérivation depuis total/qty
    qty = _qty_to_float(d.get("qty", d.get("quantity", 1)))
    tot = d.get("total_ttc_cent") or d.get("total_ht_cent")
    try:
        tot_i = int(tot or 0)
        if qty > 0:
            return int(round(tot_i / qty))
    except Exception:
        pass
    return 0


# ---------- Service ---------- #

class QuoteService:
    def __init__(self, data_dir: Optional[str | Path] = None) -> None:
        base = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data"
        base.mkdir(parents=True, exist_ok=True)
        self.repo = JsonRepository(base / "quotes.json", entity_name="quote", key="id")
        self.catalog = CatalogService()

    # ----- Recherche catalogue ----- #

    def _find_catalog_match(self, line: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Cherche par product_id / service_id / ref / label|name (insensible à la casse)."""
        pid = (line.get("product_id") or "") or None
        sid = (line.get("service_id") or "") or None
        if pid:
            try:
                p = self.catalog.get_product(pid)
                if p:
                    return p.model_dump() if hasattr(p, "model_dump") else dict(p.__dict__)
            except Exception:
                pass
        if sid:
            try:
                s = self.catalog.get_service(sid)
                if s:
                    return s.model_dump() if hasattr(s, "model_dump") else dict(s.__dict__)
            except Exception:
                pass

        ref = (line.get("ref") or "").strip()
        if ref:
            for p in self.catalog.list_products():
                if (p.ref or "").strip() == ref:
                    return p.model_dump() if hasattr(p, "model_dump") else dict(p.__dict__)
            for s in self.catalog.list_services():
                if (s.ref or "").strip() == ref:
                    return s.model_dump() if hasattr(s, "model_dump") else dict(s.__dict__)

        lbl = (line.get("label") or line.get("name") or "").strip().casefold()
        if lbl:
            for p in self.catalog.list_products():
                if ((p.label or p.name or "").strip().casefold() == lbl):
                    return p.model_dump() if hasattr(p, "model_dump") else dict(p.__dict__)
            for s in self.catalog.list_services():
                if ((s.label or s.name or "").strip().casefold() == lbl):
                    return s.model_dump() if hasattr(s, "model_dump") else dict(s.__dict__)

        return None

    # ----- Enrichissement lignes ----- #

    def _enrich_line_dict(self, line: Dict[str, Any]) -> Dict[str, Any]:
        src = self._find_catalog_match(line)

        label = line.get("label") or (src.get("label") if src else None) or (src.get("name") if src else None)
        unit = line.get("unit") if line.get("unit") is not None else ((src.get("unit") if src else "") or "")
        desc = line.get("description") or (src.get("description") if src else None) or (label or "")

        price_cents = _extract_unit_price_cents(line)
        if price_cents == 0 and src:
            price_cents = _extract_unit_price_cents(src)

        out = dict(line)
        if not out.get("ref") and src:
            out["ref"] = src.get("ref") or src.get("id") or ""

        out["label"] = label or ""
        out["unit"] = unit or ""
        out["description"] = desc or ""
        out["price_cents"] = int(price_cents)
        out["price_cent"] = int(price_cents)  # compat

        if not out.get("item_type"):
            if out.get("product_id"):
                out["item_type"] = "product"
            elif out.get("service_id"):
                out["item_type"] = "service"
            else:
                out["item_type"] = "item"
        return out

    # ----- Hydratation ----- #

    def _hydrate_line(self, d: Dict[str, Any]) -> QuoteLine:
        e = self._enrich_line_dict(d)
        qty = _qty_to_float(e.get("qty", e.get("quantity", 1)))
        pc = _extract_unit_price_cents(e)
        e["qty"] = qty
        e["total_ttc_cent"] = int(round(pc * qty))
        e["total_ht_cent"] = e["total_ttc_cent"]
        return QuoteLine.model_validate(e) if _HAS_PYDANTIC and hasattr(QuoteLine, "model_validate") else QuoteLine(**e)  # type: ignore

    def _hydrate_payment_obj(self, d: Dict[str, Any]) -> SimpleNamespace:
        at_dt = None
        for k in ("at", "date"):
            at_dt = at_dt or self._parse_dt(d.get(k))
        amount = int(d.get("amount_cent") or 0)
        return SimpleNamespace(
            at=at_dt,
            amount_cent=amount,
            method=d.get("method"),
            invoice_id=d.get("invoice_id"),
            kind=d.get("kind") or d.get("type") or "PAYMENT",
        )

    @staticmethod
    def _parse_dt(s: Any) -> Optional[datetime]:
        if not s:
            return None
        if isinstance(s, datetime):
            return s
        try:
            return datetime.fromisoformat(str(s))
        except Exception:
            return None

    def _parse_date(self, s: Any) -> Optional[date]:
        if not s:
            return None
        if isinstance(s, date) and not isinstance(s, datetime):
            return s
        try:
            return datetime.fromisoformat(str(s)).date()
        except Exception:
            return None

    def _normalize_lines_key(self, qd: Dict[str, Any]) -> List[Dict[str, Any]]:
        lines = qd.get("items", None)
        if lines is None:
            lines = qd.get("lines", [])
        if not isinstance(lines, list):
            return []
        return [_to_dict(x) for x in lines]

    def _hydrate_quote(self, d: Dict[str, Any]) -> Quote:
        qd = dict(d)
        if qd.get("event_date") and not isinstance(qd["event_date"], (date, datetime)):
            ed = self._parse_date(qd["event_date"])
            if ed:
                qd["event_date"] = ed

        raw_lines = self._normalize_lines_key(qd)
        line_objs = [self._hydrate_line(ld) for ld in raw_lines]
        total = sum(int(getattr(ln, "total_ttc_cent", 0) or 0) for ln in line_objs)

        raw_payments = qd.get("payments", [])
        pay_objs = [self._hydrate_payment_obj(_to_dict(p)) for p in raw_payments if p is not None]

        if _HAS_PYDANTIC and hasattr(Quote, "model_fields") and "items" in Quote.model_fields:  # type: ignore
            qd["items"] = [ln.model_dump() if hasattr(ln, "model_dump") else _to_dict(ln) for ln in line_objs]
        else:
            qd["lines"] = [ln.model_dump() if hasattr(ln, "model_dump") else _to_dict(ln) for ln in line_objs]

        qd["payments"] = [vars(p) for p in pay_objs]
        qd["total_ht_cent"] = total
        qd["total_ttc_cent"] = total

        q = Quote.model_validate(qd) if _HAS_PYDANTIC and hasattr(Quote, "model_validate") else Quote(**qd)  # type: ignore

        try:
            object_payments = [self._hydrate_payment_obj(_to_dict(p)) for p in (q.payments or [])]
            setattr(q, "payments", object_payments)  # type: ignore
        except Exception:
            pass
        return q

    # ----- Numérotation / CRUD / Recalc ----- #

    def _next_quote_number(self) -> str:
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
        return f"{prefix}{max_n + 1:04d}"

    def recalc_totals(self, quote: Quote | Dict[str, Any]) -> Quote | Dict[str, Any]:
        is_dict = isinstance(quote, dict)
        qd = _to_dict(quote)
        raw_lines = self._normalize_lines_key(qd)
        # recalcul robustes
        new_lines: List[Dict[str, Any]] = []
        total = 0
        for ld in raw_lines:
            e = self._enrich_line_dict(ld)
            qty = _qty_to_float(e.get("qty", e.get("quantity", 1)))
            pc = _extract_unit_price_cents(e)
            e["qty"] = qty
            e["total_ttc_cent"] = int(round(pc * qty))
            e["total_ht_cent"] = e["total_ttc_cent"]
            new_lines.append(e)
            total += e["total_ttc_cent"]

        if is_dict:
            lines_key = "items" if "items" in quote else ("lines" if "lines" in quote else "items")
            quote[lines_key] = new_lines
            quote["total_ht_cent"] = total
            quote["total_ttc_cent"] = total
            return quote

        if hasattr(quote.__class__, "model_fields") and "items" in quote.__class__.model_fields:  # type: ignore[attr-defined]
            setattr(quote, "items", [QuoteLine.model_validate(e) if _HAS_PYDANTIC and hasattr(QuoteLine, "model_validate") else QuoteLine(**e) for e in new_lines])  # type: ignore
        elif hasattr(quote, "lines"):
            setattr(quote, "lines", [QuoteLine.model_validate(e) if _HAS_PYDANTIC and hasattr(QuoteLine, "model_validate") else QuoteLine(**e) for e in new_lines])  # type: ignore
        try:
            setattr(quote, "total_ht_cent", total)
        except Exception:
            pass
        try:
            setattr(quote, "total_ttc_cent", total)
        except Exception:
            pass
        return quote

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

    def list_by_client(self, client_id: str) -> List[Quote]:
        return [self._hydrate_quote(d) for d in self.repo.find(lambda d: d.get("client_id") == client_id)]

    def load_client_map(self) -> Dict[str, Any]:
        from core.services.client_service import ClientService
        cs = ClientService()
        out: Dict[str, Any] = {}
        for c in cs.list_clients():
            cid = getattr(c, "id", None)
            if cid:
                out[cid] = c
        return out

    # ----- Export PDF ----- #

    def export_quote_pdf(self, quote: Quote | Dict[str, Any]) -> str:
        from datetime import datetime as _dt
        import pdfkit

        q = quote if isinstance(quote, Quote) else self._hydrate_quote(_to_dict(quote))
        number = getattr(q, "number", None) or "DV-XXXX-XXXX"
        created_str = getattr(q, "created_at", None)
        created_fmt = created_str.strftime("%Y-%m-%d") if hasattr(created_str, "strftime") else _dt.now().strftime("%Y-%m-%d")
        client_id = getattr(q, "client_id", None)
        client_name = f"Client {client_id or ''}".strip()

        rows_html: List[str] = []
        total_ttc_acc = 0
        raw_lines = getattr(q, "items", None) or getattr(q, "lines", []) or []

        for ln in raw_lines:
            ld = _to_dict(ln)

            # REF: si vide -> re-resolve via catalogue
            ref = (ld.get("ref") or "").strip()
            if not ref:
                src = self._find_catalog_match(ld) or {}
                ref = (src.get("ref") or src.get("id") or "").strip()

            label = (ld.get("label") or ld.get("name") or "").strip()
            desc = (ld.get("description") or label or "").strip()
            unit = (ld.get("unit") or "").strip()
            qty = _qty_to_float(ld.get("qty", ld.get("quantity", 1)))
            pc = _extract_unit_price_cents(ld)
            total = int(round(pc * qty))
            total_ttc_acc += total

            desc_html = _escape_html(desc).replace("\n", "<br>")
            rows_html.append(
                f"<tr>"
                f"<td>{_escape_html(ref)}</td>"
                f"<td><div><strong>{_escape_html(label)}</strong></div>"
                f"<div style='color:#666;font-size:12px'>{desc_html}</div></td>"
                f"<td style='text-align:center'>{_escape_html(unit)}</td>"
                f"<td style='text-align:right'>{qty:g}</td>"
                f"<td style='text-align:right'>{_cent_to_str(pc)}</td>"
                f"<td style='text-align:right'>{_cent_to_str(total)}</td>"
                f"</tr>"
            )

        total_ttc = int(getattr(q, "total_ttc_cent", total_ttc_acc) or total_ttc_acc)
        total_ht = int(getattr(q, "total_ht_cent", total_ttc) or total_ttc)

        html = f"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8"/>
<title>Devis {number}</title>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 14px; color:#111; }}
  h1 {{ font-size: 20px; margin:0 0 4px 0; }}
  .meta {{ margin-bottom: 16px; }}
  table {{ width:100%; border-collapse: collapse; }}
  th, td {{ border:1px solid #ddd; padding:8px; vertical-align: top; }}
  th {{ background:#f5f5f5; text-align:left; }}
  .totals td {{ padding:6px 8px; }}
  .right {{ text-align:right; }}
  .muted {{ color:#666; font-size:12px; }}
</style>
</head>
<body>
  <h1>Devis { _escape_html(number) }</h1>
  <div class="meta">
    <div><strong>Date :</strong> { _escape_html(created_fmt) }</div>
    <div><strong>Client :</strong> { _escape_html(client_name) }</div>
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:12%">Réf</th>
        <th>Libellé / Description</th>
        <th style="width:10%">Unité</th>
        <th style="width:10%" class="right">Qté</th>
        <th style="width:14%" class="right">Prix</th>
        <th style="width:14%" class="right">Total</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows_html) or '<tr><td colspan="6" class="muted">Aucune ligne</td></tr>'}
    </tbody>
  </table>

  <table style="width:100%; margin-top:12px; border: none;">
    <tr class="totals">
      <td style="border:none"></td><td style="border:none"></td><td style="border:none"></td>
      <td style="border:none"></td>
      <td class="right" style="border:none"><strong>Total HT</strong></td>
      <td class="right" style="border:1px solid #ddd"><strong>{_cent_to_str(total_ht)}</strong></td>
    </tr>
    <tr class="totals">
      <td style="border:none"></td><td style="border:none"></td><td style="border:none"></td>
      <td style="border:none"></td>
      <td class="right" style="border:none"><strong>Total TTC</strong></td>
      <td class="right" style="border:1px solid #ddd"><strong>{_cent_to_str(total_ttc)}</strong></td>
    </tr>
    <tr>
      <td colspan="6" class="muted">TVA non applicable, art. 293B du CGI.</td>
    </tr>
  </table>
</body>
</html>"""

        project_root = Path(__file__).resolve().parents[2]
        out_dir = project_root / "exports" / "devis"
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / f"{number}.pdf"

        wkhtml = _find_wkhtmltopdf_exe()
        if not wkhtml:
            raise RuntimeError(
                "wkhtmltopdf introuvable. Installez-le puis relancez l'application.\n"
                "Ou définissez la variable d'environnement WKHTMLTOPDF_PATH vers wkhtmltopdf.exe."
            )
        config = pdfkit.configuration(wkhtmltopdf=wkhtml)
        options = {"quiet": "", "encoding": "UTF-8", "enable-local-file-access": None}
        pdfkit.from_string(html, str(pdf_path), configuration=config, options=options)
        return str(pdf_path)
