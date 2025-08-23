from __future__ import annotations
import os, json, re
from typing import List, Optional
from math import isfinite
from pydantic import ValidationError

from core.models.quote import Quote, QuoteLine
from core.models.client import Client
from core.storage.repo import JsonRepository

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data"))
QUOTES_JSON = os.path.join(DATA_DIR, "quotes.json")
CLIENTS_JSON = os.path.join(DATA_DIR, "clients.json")
SETTINGS_JSON = os.path.join(DATA_DIR, "settings.json")

def _load_json(path: str):
    if not os.path.exists(path): return None
    with open(path, "r", encoding="utf-8") as f:
        try: return json.load(f)
        except: return None

def _dump_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def money_cent(x: float | int) -> int:
    try:
        return int(round(float(x)))
    except Exception:
        return 0

def _slug(text: str) -> str:
    # simplifié: remplace tout ce qui n’est pas alphanumérique/espaces/._- par '_'
    text = text.strip()
    text = re.sub(r"[\\/:*?\"<>|\n\r\t]", "_", text)
    text = re.sub(r"\s+", " ", text)
    return text

class QuoteService:
    def __init__(self, path: str = QUOTES_JSON):
        self.repo = JsonRepository(path, key="id")

    # ---------- CRUD ----------
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
        if not matches: return None
        try:
            return Quote(**matches[0])
        except ValidationError:
            return None

    # ---------- Calculs ----------
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

    # ---------- Clients ----------
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

    # ---------- Numérotation ----------
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

    # ---------- Export PDF/HTML ----------
    def export_quote_pdf(self, q: Quote, out_dir: Optional[str] = None) -> str:
        """
        1) Rend HTML via Jinja
        2) Tente PDF via WeasyPrint
        3) Sinon tente PDF via wkhtmltopdf (pdfkit)
        4) Sinon garde HTML
        Retourne le chemin du fichier final.
        """
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        templates_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "templates", "pdf"))
        env = Environment(loader=FileSystemLoader(templates_dir), autoescape=select_autoescape())
        tpl = env.get_template("quote.html")

        clients = self.load_client_map()
        client = clients.get(q.client_id)
        client_name = _slug(getattr(client, "name", "") or "Client")

        settings = _load_json(SETTINGS_JSON) or {}
        company = settings.get("company", {})

        def cent_to_eur(c: int) -> str:
            return f"{c/100:.2f} €"

        html = tpl.render(
            quote={
                "number": q.number,
                "lines": [
                    {
                        "label": ln.label,
                        "qty": ln.qty,
                        "unit_price_ttc": cent_to_eur(ln.unit_price_ttc_cent),
                        "total_ttc": cent_to_eur(ln.total_line_ttc_cent),
                    } for ln in q.lines
                ],
                "total_ttc": cent_to_eur(q.total_ttc_cent),
            },
            client={
                "name": getattr(client, "name", ""),
                "email": getattr(client, "email", ""),
            },
            company={
                "name": company.get("name", "Ma Société"),
                "email": company.get("email", ""),
                "address": company.get("address", ""),
            },
        )

        exports_dir = out_dir or os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "exports"))
        os.makedirs(exports_dir, exist_ok=True)

        base_name = f"{q.number or q.id}_devis ({client_name})"
        base = os.path.join(exports_dir, base_name)

        # 1) Sauvegarde HTML (toujours)
        html_path = base + ".html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # 2) Tentative PDF via WeasyPrint
        try:
            import weasyprint
            pdf_path = base + ".pdf"
            weasyprint.HTML(string=html, base_url=templates_dir).write_pdf(pdf_path)
            return pdf_path
        except Exception:
            pass

        # 3) Tentative PDF via wkhtmltopdf (pdfkit)
        try:
            import pdfkit
            wkhtml_path = (settings.get("pdf", {}) or {}).get("wkhtmltopdf_path")
            config = pdfkit.configuration(wkhtmltopdf=wkhtml_path) if wkhtml_path else None
            css_path = os.path.join(templates_dir, "stylesheet.css")
            pdf_path = base + ".pdf"
            # options minimalistes; wkhtmltopdf est verbeux sans quiet
            opts = {"quiet": ""}
            pdfkit.from_string(html, pdf_path, options=opts, configuration=config, css=css_path)
            return pdf_path
        except Exception:
            # 4) Retourne HTML si tout échoue
            return html_path
