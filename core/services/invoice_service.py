from __future__ import annotations
import os, json, re
from typing import List, Optional, Literal
from pydantic import ValidationError
from core.models.invoice import Invoice, InvoiceLine
from core.models.quote import Quote
from core.models.client import Client
from core.storage.repo import JsonRepository

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data"))
INVOICES_JSON = os.path.join(DATA_DIR, "invoices.json")
QUOTES_JSON = os.path.join(DATA_DIR, "quotes.json")
CLIENTS_JSON = os.path.join(DATA_DIR, "clients.json")
SETTINGS_JSON = os.path.join(DATA_DIR, "settings.json")

def _load_json(path: str):
    if not os.path.exists(path): return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _dump_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _slug(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"[\\/:*?\"<>|\n\r\t]", "_", text)
    text = re.sub(r"\s+", " ", text)
    return text or "Client"

class InvoiceService:
    def __init__(self, path: str = INVOICES_JSON):
        self.repo = JsonRepository(path, key="id")

    # ----------- CRUD/list -----------
    def list_invoices(self) -> List[Invoice]:
        out: List[Invoice] = []
        for d in self.repo.list_all():
            try:
                out.append(Invoice(**d))
            except ValidationError:
                continue
        return out

    def list_by_quote(self, quote_id: str) -> List[Invoice]:
        out: List[Invoice] = []
        for d in self.repo.find(lambda x: x.get("quote_id") == quote_id):
            try:
                out.append(Invoice(**d))
            except ValidationError:
                continue
        return out

    def get_by_id(self, invoice_id: str) -> Optional[Invoice]:
        m = self.repo.find(lambda x: x.get("id") == invoice_id)
        if not m: return None
        try:
            return Invoice(**m[0])
        except ValidationError:
            return None

    def update_invoice(self, inv: Invoice) -> Invoice:
        self.repo.update(inv.model_dump())
        return inv

    def add_invoice(self, inv: Invoice) -> Invoice:
        # numéro auto
        if not inv.number:
            inv.number = self._next_invoice_number(inv.type)
        # total (somme des lignes)
        inv.total_ttc_cent = sum(ln.total_line_ttc_cent for ln in inv.lines)
        self.repo.add(inv.model_dump())
        return inv

    # ----------- génération -----------
    def gen_deposit(self, q: Quote, pct: Optional[float] = None, explicit_amount: Optional[int] = None) -> Invoice:
        if explicit_amount is not None:
            amount = int(explicit_amount)
        else:
            s = _load_json(SETTINGS_JSON) or {}
            default_pct = float((s.get("acompte_pct") or 30))
            deposit_pct = float(pct if pct is not None else default_pct)
            deposit_pct = max(0.0, min(100.0, deposit_pct))
            amount = int(round(q.total_ttc_cent * (deposit_pct / 100.0)))

        inv = Invoice(
            type="ACOMPTE", status="ISSUED",
            quote_id=q.id, client_id=q.client_id,
            lines=[InvoiceLine(label=f"Acompte sur devis {q.number}", qty=1.0,
                               unit_price_ttc_cent=amount, total_line_ttc_cent=amount)],
            total_ttc_cent=amount,
            notes="TVA non applicable, art. 293 B du CGI."
        )
        return self.add_invoice(inv)

    def gen_balance(self, q: Quote, explicit_amount: Optional[int] = None) -> Invoice:
        if explicit_amount is not None:
            remaining = int(explicit_amount)
        else:
            remaining = q.remaining_cent()
        inv = Invoice(
            type="SOLDE", status="ISSUED",
            quote_id=q.id, client_id=q.client_id,
            lines=[InvoiceLine(label=f"Solde sur devis {q.number}", qty=1.0,
                               unit_price_ttc_cent=remaining, total_line_ttc_cent=remaining)],
            total_ttc_cent=remaining,
            notes="TVA non applicable, art. 293 B du CGI."
        )
        return self.add_invoice(inv)

    def gen_final(self, q: Quote) -> Invoice:
        inv = Invoice(
            type="FINALE", status="ISSUED",
            quote_id=q.id, client_id=q.client_id,
            lines=[InvoiceLine(label=f"Facture finale – devis {q.number}", qty=1.0,
                               unit_price_ttc_cent=0, total_line_ttc_cent=0)],
            total_ttc_cent=0,
            notes="TVA non applicable, art. 293 B du CGI."
        )
        return self.add_invoice(inv)

    def gen_final(self, q: Quote) -> Invoice:
        # Récapitulatif avec rappel du total du devis
        inv = Invoice(
            type="FINALE",
            status="ISSUED",
            quote_id=q.id,
            client_id=q.client_id,
            lines=[InvoiceLine(label=f"Facture finale – Récap devis {q.number}", qty=1.0,
                               unit_price_ttc_cent=0, total_line_ttc_cent=0)],
            total_ttc_cent=0,
            notes="TVA non applicable, art. 293 B du CGI."
        )
        return self.add_invoice(inv)

    # ----------- numérotation -----------
    def _next_invoice_number(self, inv_type: str) -> str:
        s = _load_json(SETTINGS_JSON) or {}
        numbering = s.get("numbering", {})
        base_prefix = numbering.get("invoice_prefix", "FAC-")
        t_map = {"ACOMPTE": "A", "SOLDE": "S", "FINALE": "F"}
        prefix = f"{base_prefix}{t_map.get(inv_type, 'X')}-"
        seq_key = f"invoice_seq_{t_map.get(inv_type, 'X')}"
        seq = numbering.get(seq_key, 1)
        number = f"{prefix}{seq:04d}"
        numbering[seq_key] = seq + 1
        s["numbering"] = numbering
        _dump_json(SETTINGS_JSON, s)
        return number

    # ----------- clients ----------
    def _client_name(self, client_id: str) -> str:
        data = _load_json(CLIENTS_JSON) or []
        for d in data:
            try:
                c = Client(**d)
            except ValidationError:
                continue
            if c.id == client_id:
                return c.name
        return "Client"

    # ----------- export PDF ----------
    def export_invoice_pdf(self, inv: Invoice, out_dir: Optional[str] = None) -> str:
        """
        1) HTML via Jinja
        2) PDF via WeasyPrint
        3) Fallback wkhtmltopdf (pdfkit)
        4) Sinon HTML
        """
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        import traceback

        templates_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "templates", "pdf"))
        env = Environment(loader=FileSystemLoader(templates_dir), autoescape=select_autoescape())
        tpl = env.get_template("invoice.html")

        client_name = _slug(self._client_name(inv.client_id))
        settings = _load_json(SETTINGS_JSON) or {}
        company = settings.get("company", {})

        def cent_to_eur(c: int) -> str:
            return f"{c/100:.2f} €"

        html = tpl.render(
            invoice={
                "number": inv.number,
                "type": inv.type,
                "lines": [
                    {
                        "label": ln.label,
                        "qty": ln.qty,
                        "unit_price_ttc": cent_to_eur(ln.unit_price_ttc_cent),
                        "total_ttc": cent_to_eur(ln.total_line_ttc_cent),
                    } for ln in inv.lines
                ],
                "total_ttc": cent_to_eur(inv.total_ttc_cent),
            },
            client={"name": self._client_name(inv.client_id)},
            company={
                "name": company.get("name", "Ma Société"),
                "email": company.get("email", ""),
                "address": company.get("address", ""),
            },
        )

        exports_dir = out_dir or os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "exports"))
        os.makedirs(exports_dir, exist_ok=True)

        type_code = {"ACOMPTE": "FAC-A", "SOLDE": "FAC-S", "FINALE": "FAC-F"}.get(inv.type, "FAC-X")
        base_name = f"{type_code}-{(inv.number or inv.id).split('-')[-1]} ({client_name})"
        base = os.path.join(exports_dir, base_name)

        html_path = base + ".html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)

        # WeasyPrint
        try:
            import weasyprint
            pdf_path = base + ".pdf"
            weasyprint.HTML(string=html, base_url=templates_dir).write_pdf(pdf_path)
            return pdf_path
        except Exception:
            pass

        # wkhtmltopdf
        try:
            import pdfkit
            css_path = os.path.join(templates_dir, "stylesheet.css")
            pdf_path = base + ".pdf"
            opts = {"quiet": "", "enable-local-file-access": ""}
            wkhtml_path = (settings.get("pdf", {}) or {}).get("wkhtmltopdf_path")
            if wkhtml_path and os.path.exists(wkhtml_path):
                config = pdfkit.configuration(wkhtmltopdf=wkhtml_path)
                pdfkit.from_string(html, pdf_path, options=opts, configuration=config, css=css_path)
            else:
                pdfkit.from_string(html, pdf_path, options=opts, css=css_path)
            return pdf_path
        except Exception:
            log_path = base + ".log"
            import traceback
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write("PDF generation error:\n")
                lf.write(traceback.format_exc())
            return html_path
