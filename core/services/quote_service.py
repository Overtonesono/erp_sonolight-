# core/services/quote_service.py
from __future__ import annotations

import os
import json
import re
from typing import List, Optional
from math import isfinite
from pathlib import Path

from pydantic import ValidationError
import pdfkit  # utilisé si wkhtmltopdf est présent

from core.models.quote import Quote, QuoteLine
from core.models.client import Client
from core.storage.repo import JsonRepository

# --- Chemins de base ---
ROOT_DIR = Path(__file__).resolve().parents[2]  # erp_sonolight/
DATA_DIR = ROOT_DIR / "data"
TEMPLATES_DIR = ROOT_DIR / "templates" / "pdf"
EXPORTS_DIR = ROOT_DIR / "exports"

QUOTES_JSON = DATA_DIR / "quotes.json"
CLIENTS_JSON = DATA_DIR / "clients.json"
SETTINGS_JSON = DATA_DIR / "settings.json"

DEF_TERMS = (
    "Conditions de paiement : 30% à l'acceptation du devis, 70% au plus tard le jour de l'évènement. "
    "TVA non applicable, art. 293 B du CGI. Devis valable 30 jours."
)

# ---------- Utils JSON ----------
def _load_json(path: os.PathLike | str):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _dump_json(path: os.PathLike | str, data) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ---------- Monnaie ----------
def money_cent(x: float | int) -> int:
    try:
        return int(round(float(x)))
    except Exception:
        return 0

def cent_to_eur(cents: int) -> float:
    try:
        return round(int(cents) / 100.0, 2)
    except Exception:
        return 0.0

# ---------- Divers ----------
def _slug(text: str) -> str:
    # remplace caractères interdits Windows
    text = text.strip()
    text = re.sub(r'[\\/:*?"<>|\n\r\t]', "_", text)
    text = re.sub(r"\s+", " ", text)
    return text

# ---------- Service ----------
class QuoteService:
    def __init__(self, path: os.PathLike | str = QUOTES_JSON):
        self.repo = JsonRepository(str(path), key="id")

    # ----- CRUD -----
    def list_quotes(self) -> List[Quote]:
        out: List[Quote] = []
        for d in self.repo.list_all():
            try:
                out.append(Quote(**d))
            except ValidationError:
                continue
        return out

    def add_quote(self, q: Quote) -> Quote:
        if not q.number:
            q.number = self._next_quote_number()
        self.recalc_totals(q)
        self.repo.add(q.model_dump())
        return q

    def update_quote(self, q: Quote) -> Quote:
        self.recalc_totals(q)
        self.repo.update(q.model_dump())
        return q

    def delete_quote(self, quote_id: str) -> None:
        self.repo.delete(quote_id)

    def get_by_id(self, quote_id: str) -> Optional[Quote]:
        matches = self.repo.find(lambda d: d.get("id") == quote_id)
        if not matches:
            return None
        try:
            return Quote(**matches[0])
        except ValidationError:
            return None

    # ----- Calculs -----
    def recalc_totals(self, q: Quote) -> None:
        total = 0
        for ln in q.lines:
            qty = float(ln.qty) if isfinite(float(ln.qty)) else 0.0
            brut = int(round(qty * ln.unit_price_ttc_cent))
            rem = max(0.0, min(100.0, float(ln.remise_pct)))
            net = int(round(brut * (1.0 - rem / 100.0)))
            ln.total_line_ttc_cent = net
            total += net
        q.total_ttc_cent = total

    # ----- Clients -----
    def load_client_map(self) -> dict[str, Client]:
        data = _load_json(CLIENTS_JSON) or []
        out: dict[str, Client] = {}
        for d in data:
            try:
                c = Client(**d)
                out[c.id] = c
            except ValidationError:
                continue
        return out

    # ----- Numérotation -----
    def _next_quote_number(self) -> str:
        settings = _load_json(SETTINGS_JSON) or {}
        numbering = settings.get("numbering", {})
        prefix = numbering.get("quote_prefix", "DEV-")
        seq = numbering.get("sequence", 1)
        number = f"{prefix}{seq:04d}"
        numbering["sequence"] = seq + 1
        settings["numbering"] = numbering
        _dump_json(SETTINGS_JSON, settings)
        return number

    # ---------- Rendu HTML (Jinja) ----------
    def _render_quote_html(self, q: Quote) -> str:
        """
        Rend le HTML du devis en mémoire à partir du template Jinja2 'templates/pdf/quote.html'.
        """
        from jinja2 import Environment, FileSystemLoader, select_autoescape

        env = Environment(
            loader=FileSystemLoader(str(TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"])
        )
        tpl = env.get_template("quote.html")

        clients = self.load_client_map()
        client = clients.get(q.client_id) if q.client_id else None
        client_name = getattr(client, "name", "") or "Client"

        settings = _load_json(SETTINGS_JSON) or {}
        company = settings.get("company", {}) if isinstance(settings, dict) else {}

        terms = getattr(q, "terms", None) or settings.get("default_terms") or DEF_TERMS

        ctx = {
            "quote": {
                "number": q.number,
                "event_date": q.event_date.isoformat() if q.event_date else None,
                "lines": [
                    {
                        "label": ln.label,
                        "description": ln.description or "",
                        "qty": ln.qty,
                        "unit_price_ttc": cent_to_eur(ln.unit_price_ttc_cent),
                        "remise_pct": ln.remise_pct,
                        "total_ttc": cent_to_eur(ln.total_line_ttc_cent),
                    }
                    for ln in q.lines
                ],
                "total_ttc": cent_to_eur(q.total_ttc_cent),
            },
            "client": {
                "name": getattr(client, "name", ""),
                "email": getattr(client, "email", ""),
                "address": getattr(client, "address", ""),
                "phone": getattr(client, "phone", ""),
            },
            "company": {
                "name": company.get("name", "Ma Société"),
                "email": company.get("email", ""),
                "address": company.get("address", ""),
                "siret": company.get("siret", ""),
            },
            "terms": terms,
        }

        return tpl.render(**ctx)

    # ---------- PDF ----------
    def export_quote_pdf(self, q: Quote) -> Path:
        """
        Génére le PDF du devis sans créer de fichier HTML intermédiaire.
        Essaie wkhtmltopdf (pdfkit) d'abord, puis WeasyPrint en fallback.
        """
        html = self._render_quote_html(q)

        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_client = _slug(getattr(self.load_client_map().get(q.client_id) or object(), "name", "") or "Client")
        filename = f"{q.number or q.id}_devis_{safe_client}.pdf"
        out_path = EXPORTS_DIR / "devis" / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)

        base_url = str(TEMPLATES_DIR.resolve())

        wkhtml = _find_wkhtmltopdf()
        if wkhtml:
            try:
                config = pdfkit.configuration(wkhtmltopdf=wkhtml)
                options = {
                    "enable-local-file-access": None,
                    "quiet": "",
                    "encoding": "UTF-8",
                }
                css_path = str((TEMPLATES_DIR / "stylesheet.css").resolve())
                pdfkit.from_string(html, str(out_path), options=options, configuration=config, css=css_path)
                return out_path
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Échec wkhtmltopdf (%s). Fallback WeasyPrint...", e)

        # Fallback WeasyPrint
        _render_pdf_with_weasyprint(html, out_path, base_url=base_url)
        return out_path


# ---------- Helpers PDF ----------
def _clean_path(p: str) -> str:
    """
    Nettoie un chemin mal échappé type 'C\\:\\Program Files\\...' -> 'C:\\Program Files\\...'
    """
    if not p:
        return ""
    p = p.strip().strip('"').strip("'")
    p = p.replace("\\:", ":")  # corrige 'C\:\' -> 'C:\'
    return os.path.normpath(p)

def _find_wkhtmltopdf() -> Optional[str]:
    """
    Localise wkhtmltopdf.exe :
    - Variables d'env (WKHTMLTOPDF, WKHTMLTOPDF_CMD)
    - settings.json -> pdf.wkhtmltopdf_path ou wkhtmltopdf_path
    - chemins Windows connus
    - PATH
    """
    # 1) Env
    for env_key in ("WKHTMLTOPDF", "WKHTMLTOPDF_CMD"):
        val = os.environ.get(env_key)
        if val:
            path = _clean_path(val)
            if Path(path).is_file():
                return path

    # 2) settings.json
    s = _load_json(SETTINGS_JSON) or {}
    if isinstance(s, dict):
        pdf_conf = s.get("pdf", {}) if isinstance(s.get("pdf"), dict) else {}
        for key in ("wkhtmltopdf_path",):
            wk = pdf_conf.get(key) or s.get(key)
            if wk:
                path = _clean_path(wk)
                if Path(path).is_file():
                    return path

    # 3) Chemins Windows fréquents
    candidates = [
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
    ]
    for c in candidates:
        if Path(c).is_file():
            return c

    # 4) PATH
    from shutil import which
    found = which("wkhtmltopdf")
    if found:
        return _clean_path(found)

    return None

def _render_pdf_with_weasyprint(html: str, out_path: Path, base_url: Optional[str]) -> None:
    """
    Fallback WeasyPrint (ne nécessite pas wkhtmltopdf).
    """
    try:
        from weasyprint import HTML, CSS
    except Exception as e:
        raise RuntimeError(
            "Aucun wkhtmltopdf trouvé et WeasyPrint n'est pas installé. "
            "Installe WeasyPrint (pip install weasyprint) ou configure wkhtmltopdf.\n"
            f"Détails: {e}"
        ) from e

    css_file = TEMPLATES_DIR / "stylesheet.css"
    styles = [CSS(filename=str(css_file))] if css_file.exists() else None
    HTML(string=html, base_url=base_url).write_pdf(str(out_path), stylesheets=styles)
