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
        # attention au chemin de ton projet
from core.services.catalog_service import CatalogService
from core.models.quote import Quote, QuoteLine


# ---------- Helpers génériques ---------- #

def _cent_to_str(c: int) -> str:
    try:
        return f"{(c or 0) / 100:.2f} €"
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
    # Emplacements Windows fréquents
    candidates = [
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files\wkhtmltopdf\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\wkhtmltopdf.exe",
    ]
    for c in candidates:
        import os
        if os.path.isfile(c):
            return c
    return None

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
    """
    Retourne un prix en CENTIMES depuis divers champs possibles.
    Gère virgules, espaces, symbole €, etc.
    """
    from decimal import Decimal, InvalidOperation
    import re

    # Champs déjà en centimes
    for k in ("price_cents", "price_cent", "price_ttc_cent", "price_ht_cent", "unit_price_cent", "unit_price_cents"):
        if k in payload and payload[k] not in (None, ""):
            try:
                return max(0, int(payload[k]))
            except Exception:
                pass

    def _clean_to_decimal(val: Any) -> Optional[Decimal]:
        if val is None or val == "":
            return None
        if isinstance(val, (int, float)):
            try:
                return Decimal(str(val))
            except Exception:
                return None
        s = str(val)
        s = re.sub(r"[^0-9,.\-]", "", s)  # enlève € et espaces
        s = s.replace(",", ".")
        try:
            return Decimal(s)
        except (InvalidOperation, ValueError):
            return None

    # Champs en euros usuels
    euro_keys = ("price_eur", "price", "unit_price_eur", "unit_price", "priceTtcEur", "ttc_eur")
    for k in euro_keys:
        if k in payload and payload[k] not in (None, ""):
            d = _clean_to_decimal(payload[k])
            if d is not None:
                return max(0, int(d * 100))  # arrondi vers 0 → suffisant ici

    # Fallback: toute clé contenant 'price'
    for k, v in payload.items():
        if "price" in k.lower() and v not in (None, ""):
            d = _clean_to_decimal(v)
            if d is not None:
                return max(0, int(d * 100))

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


# ---------- Service ---------- #

class QuoteService:
    def __init__(self, data_dir: Optional[str | Path] = None) -> None:
        base = Path(data_dir) if data_dir else Path(__file__).resolve().parents[2] / "data"
        base.mkdir(parents=True, exist_ok=True)
        self.repo = JsonRepository(base / "quotes.json", entity_name="quote", key="id")
        self.catalog = CatalogService()

    # ----- Recherche catalogue robuste ----- #

    def _find_catalog_match(self, line: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Tente dans l'ordre :
        - product_id / service_id
        - ref exacte
        - label/name (insensible à la casse, trim)
        Retourne le dict source (product/service) si trouvé.
        """
        # 1) Par ID direct
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

        # 2) Par ref
        ref = (line.get("ref") or "").strip()
        if ref:
            for p in self.catalog.list_products():
                if ((p.ref or "").strip() == ref):
                    return p.model_dump() if hasattr(p, "model_dump") else dict(p.__dict__)
            for s in self.catalog.list_services():
                if ((s.ref or "").strip() == ref):
                    return s.model_dump() if hasattr(s, "model_dump") else dict(s.__dict__)

        # 3) Par label / name (fallback)
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
        """
        Complète la ligne dict: description, label, unit, price_cents si manquants
        depuis le catalogue (product_id/service_id, ref, ou label/name).
        Gère les prix en euros et centimes, et duplique en price_cent (compat).
        """
        src: Optional[Dict[str, Any]] = self._find_catalog_match(line)

        # Libellé / Unité / Description
        label = line.get("label") or (src.get("label") if src else None) or (src.get("name") if src else None)
        unit = line.get("unit") if line.get("unit") is not None else ((src.get("unit") if src else "") or "")
        desc = line.get("description") or (src.get("description") if src else None) or (label or "")

        # Prix : priorité à la ligne, sinon fiche catalogue
        price_cents = _price_to_cents(_to_dict(line))
        if (price_cents in (None, "", 0)) and src:
            price_cents = _price_to_cents(src)
        try:
            price_cents = int(price_cents or 0)
        except Exception:
            price_cents = 0

        out = dict(line)

        # Remplir ref depuis la source si non renseignée
        if not out.get("ref") and src:
            out["ref"] = src.get("ref") or src.get("id") or ""

        out["label"] = label or ""
        out["unit"] = unit or ""
        out["description"] = desc or ""

        # Ecrire les deux clés pour compat Pydantic/modèles hétérogènes
        out["price_cents"] = price_cents
        out["price_cent"] = price_cents

        if not out.get("item_type"):
            if out.get("product_id"):
                out["item_type"] = "product"
            elif out.get("service_id"):
                out["item_type"] = "service"
            else:
                out["item_type"] = "item"
        return out

    # ----- Hydratation Pydantic ----- #

    def _hydrate_line(self, d: Dict[str, Any]) -> QuoteLine:
        e = self._enrich_line_dict(d)

        # Ultime sécurité si 0 et que la source brute a un autre champ prix
        if int(e.get("price_cents") or 0) == 0 and int(e.get("price_cent") or 0) == 0:
            pc = _price_to_cents(_to_dict(d))
            if pc:
                e["price_cents"] = int(pc)
                e["price_cent"] = int(pc)

        qty = _qty_to_float(e.get("qty", e.get("quantity", 1)))
        pc = int(e.get("price_cents") or e.get("price_cent") or 0)

        e["qty"] = qty
        e["total_ttc_cent"] = int(round(pc * qty))  # TTC = HT (293B)
        # ne jamais perdre total si le modèle droppe des champs
        e["total_ht_cent"] = e["total_ttc_cent"]

        return (QuoteLine.model_validate(e)
                if _HAS_PYDANTIC and hasattr(QuoteLine, "model_validate")
                else QuoteLine(**e))  # type: ignore

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

        qd["payments"] = [vars(p) for p in pay_objs]
        qd["total_ht_cent"] = total
        qd["total_ttc_cent"] = total

        q = Quote.model_validate(qd) if _HAS_PYDANTIC and hasattr(Quote, "model_validate") else Quote(**qd)  # type: ignore

        # remplacer q.payments par objets simples (at, amount_cent…)
        try:
            object_payments = [self._hydrate_payment_obj(_to_dict(p)) for p in (q.payments or [])]
            setattr(q, "payments", object_payments)  # type: ignore
        except Exception:
            pass

        return q

    # ----- Numérotation ----- #

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
        return f"{prefix}{max_n + 1:04d}"

    # ----- Recalcul (appel UI) ----- #

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
        try:
            setattr(quote, "total_ht_cent", total)
        except Exception:
            pass
        try:
            setattr(quote, "total_ttc_cent", total)
        except Exception:
            pass
        return quote

    # ----- CRUD (retours hydratés) ----- #

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

    # ----- Divers ----- #

    def list_by_client(self, client_id: str) -> List[Quote]:
        return [self._hydrate_quote(d) for d in self.repo.find(lambda d: d.get("client_id") == client_id)]

    def load_client_map(self) -> Dict[str, Any]:
        """
        Retourne un dict {client_id: Client} utilisé par l'UI (MainWindow).
        Import local pour éviter les imports circulaires.
        """
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
        """
        Génère un PDF de devis dans exports/devis/<NUMERO>.pdf (PDF SEULEMENT).
        Utilise wkhtmltopdf via pdfkit. Pas de HTML persistant.
        Lève une erreur claire si wkhtmltopdf introuvable.
        """
        from datetime import datetime as _dt
        from pathlib import Path
        import pdfkit

        # Toujours re-hydrater pour s'assurer que totaux/prix/refs sont cohérents
        q = quote if isinstance(quote, Quote) else self._hydrate_quote(_to_dict(quote))
        number = getattr(q, "number", None) or "DV-XXXX-XXXX"
        created_str = getattr(q, "created_at", None)
        created_fmt = created_str.strftime("%Y-%m-%d") if hasattr(created_str, "strftime") else _dt.now().strftime("%Y-%m-%d")
        client_id = getattr(q, "client_id", None)
        client_name = f"Client {client_id or ''}".strip()

        # Lignes -> toujours passer par dict pour lire prix/ref/qty proprement
        raw_lines = getattr(q, "items", None) or getattr(q, "lines", []) or []
        rows_html: List[str] = []
        total_ttc_acc = 0

        for ln in raw_lines:
            ld = _to_dict(ln)
            ref = (ld.get("ref") or "").strip()
            label = (ld.get("label") or ld.get("name") or "").strip()
            desc = (ld.get("description") or label or "").strip()
            unit = (ld.get("unit") or "").strip()
            qty = _qty_to_float(ld.get("qty", ld.get("quantity", 1)))
            pc = _price_to_cents(ld)
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

        # Totaux
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
        options = {
            "quiet": "",
            "encoding": "UTF-8",
            "enable-local-file-access": None,
        }
        pdfkit.from_string(html, str(pdf_path), configuration=config, options=options)
        return str(pdf_path)
