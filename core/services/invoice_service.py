from __future__ import annotations
import os, json, re
from pathlib import Path
import pdfkit  # utilisé si wkhtmltopdf dispo
from typing import List, Optional, Literal
from pydantic import ValidationError
from core.models.invoice import Invoice, InvoiceLine
from core.models.quote import Quote
from core.models.client import Client
from core.storage.repo import JsonRepository

ROOT_DIR = Path(__file__).resolve().parents[2]  # erp_sonolight/
TEMPLATES_DIR = ROOT_DIR / "templates" / "pdf"
EXPORTS_DIR = ROOT_DIR / "exports"
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data"))
INVOICES_JSON = os.path.join(DATA_DIR, "invoices.json")
QUOTES_JSON = os.path.join(DATA_DIR, "quotes.json")
CLIENTS_JSON = os.path.join(DATA_DIR, "clients.json")
SETTINGS_JSON = os.path.join(DATA_DIR, "settings.json")

def _load_json(path: os.PathLike | str):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _clean_path(p: str) -> str:
    """Corrige 'C\\:\\Program Files\\...' -> 'C:\\Program Files\\...' et normalise."""
    if not p:
        return ""
    p = p.strip().strip('"').strip("'")
    p = p.replace("\\:", ":")
    return os.path.normpath(p)

def _find_wkhtmltopdf() -> Optional[str]:
    """Détecte wkhtmltopdf via env, settings.json, chemins connus, PATH."""
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
        wk = pdf_conf.get("wkhtmltopdf_path") or s.get("wkhtmltopdf_path")
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
    """Fallback WeasyPrint (si wkhtmltopdf absent)."""
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

def _cent_to_eur(cents: int) -> float:
    try:
        return round(int(cents) / 100.0, 2)
    except Exception:
        return 0.0

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
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        templates_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "templates", "pdf"))
        env = Environment(loader=FileSystemLoader(templates_dir), autoescape=select_autoescape())
        tpl = env.get_template("invoice.html")

        def _load_json(path: str):
            if not os.path.exists(path): return None
            try:
                with open(path, "r", encoding="utf-8") as f: return json.load(f)
            except Exception: return None

        def cent_to_eur(c: int) -> str:
            return f"{c/100:.2f} €"

        settings = _load_json(SETTINGS_JSON) or {}
        company = settings.get("company", {})

        # client name helper
        cname = "Client"
        data = _load_json(CLIENTS_JSON) or []
        from pydantic import ValidationError
        from core.models.client import Client
        for d in data:
            try:
                c = Client(**d)
                if c.id == inv.client_id:
                    cname = c.name; break
            except ValidationError:
                continue

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
            client={"name": cname},
            company={
                "name": company.get("name", "Ma Société"),
                "email": company.get("email", ""),
                "address": company.get("address", ""),
                "siret": company.get("siret", ""),
            },
        )

        exports_dir = out_dir or os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "exports", "factures"))
        os.makedirs(exports_dir, exist_ok=True)
        type_code = {"ACOMPTE": "FAC-A", "SOLDE": "FAC-S", "FINALE": "FAC-F"}.get(inv.type, "FAC-X")
        tail = (inv.number or inv.id).split("-")[-1]
        base_name = f"{type_code}-{tail} ({cname})"; base = os.path.join(exports_dir, base_name)
        pdf_path = base + ".pdf"

        # Try WeasyPrint
        try:
            import weasyprint
            weasyprint.HTML(string=html, base_url=templates_dir).write_pdf(pdf_path, stylesheets=[weasyprint.CSS(os.path.join(templates_dir, "stylesheet.css"))])
            return pdf_path
        except Exception:
            pass

        # Fallback wkhtmltopdf
        try:
            import pdfkit
            css_path = os.path.join(templates_dir, "stylesheet.css")
            settings_pdf = settings.get("pdf", {}) if settings else {}
            wkhtml_path = settings_pdf.get("wkhtmltopdf_path")
            config = pdfkit.configuration(wkhtmltopdf=wkhtml_path) if wkhtml_path else None
            opts = {"quiet": "", "enable-local-file-access": ""}
            pdfkit.from_string(html, pdf_path, options=opts, configuration=config, css=css_path)
            return pdf_path
        except Exception as e:
            raise RuntimeError(f"Échec génération PDF: {e}")
