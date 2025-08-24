from __future__ import annotations
import os, json, re
from typing import List, Optional
from math import isfinite
from pydantic import ValidationError
from pathlib import Path
from typing import Optional
import pdfkit

from core.models.quote import Quote, QuoteLine
from core.models.client import Client
from core.storage.repo import JsonRepository

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data"))
QUOTES_JSON = os.path.join(DATA_DIR, "quotes.json")
CLIENTS_JSON = os.path.join(DATA_DIR, "clients.json")
SETTINGS_JSON = os.path.join(DATA_DIR, "settings.json")

DEF_TERMS = (
    "Conditions de paiement : 30% à l'acceptation du devis, 70% au plus tard le jour de l'évènement. "
    "TVA non applicable, art. 293 B du CGI. Devis valable 30 jours."
)

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

def _clean_path(p: str) -> str:
    """Nettoie un chemin potentiellement mal échappé type 'C\\:\\Program Files\\...'
    et retourne un chemin Windows valide style 'C:\\Program Files\\...'
    """
    if not p:
        return ""
    # Retire quotes parasites
    p = p.strip().strip('"').strip("'")
    # Corrige le pattern 'C\\:\' -> 'C:\'
    p = p.replace("\\:", ":")
    # Normalise
    return os.path.normpath(p)


def _find_wkhtmltopdf(settings_path: Optional[str] = None) -> Optional[str]:
    """Tente de localiser wkhtmltopdf.exe.
    Priorités : var d'env -> settings.json -> chemins connus.
    Retourne un chemin utilisable ou None.
    """
    # 1) Variables d'environnement possibles
    for env_key in ("WKHTMLTOPDF", "WKHTMLTOPDF_CMD"):
        val = os.environ.get(env_key)
        if val:
            path = _clean_path(val)
            if Path(path).is_file():
                return path

    # 2) settings.json si tu stockes un chemin (optionnel)
    #    Exemple: {"wkhtmltopdf_path": "C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe"}
    try:
        from core.storage.settings_repo import SettingsRepo  # si tu as un repo de settings
        repo = SettingsRepo()
        s = repo.load()
        wk = s.get("wkhtmltopdf_path")
        if wk:
            path = _clean_path(wk)
            if Path(path).is_file():
                return path
    except Exception:
        # Repo de settings absent ou non utilisé -> ignore
        pass

    # 3) Chemins Windows habituels
    candidates = [
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
    ]
    for c in candidates:
        if Path(c).is_file():
            return c

    # 4) PATH système
    from shutil import which
    found = which("wkhtmltopdf")
    if found:
        return _clean_path(found)

    return None


def _render_pdf_with_weasyprint(html: str, out_path: Path, base_url: Optional[str]) -> None:
    """Fallback WeasyPrint (ne nécessite pas wkhtmltopdf)."""
    try:
        from weasyprint import HTML
    except Exception as e:
        raise RuntimeError(
            "Aucun wkhtmltopdf trouvé et WeasyPrint n'est pas installé. "
            "Installe WeasyPrint (pip install weasyprint) ou fournis un chemin wkhtmltopdf.\n"
            f"Détails: {e}"
        ) from e

    HTML(string=html, base_url=base_url).write_pdf(str(out_path))


def export_quote_pdf(self, quote) -> Path:
    """Génère le PDF du devis sans créer d'HTML temporaire.
    Utilise wkhtmltopdf si dispo, sinon WeasyPrint.
    """
    # 1) Génère le HTML en mémoire
    html = self._render_quote_html(quote)  # suppose que tu as déjà cette méthode
    exports_dir = Path("exports")
    exports_dir.mkdir(parents=True, exist_ok=True)
    out_path = exports_dir / f"devis_{quote.number}.pdf"

    # Pour les ressources (CSS, images) résolues depuis templates/pdf/
    base_url = str(Path("templates").resolve())

    # 2) Tente wkhtmltopdf d'abord
    wkhtml = _find_wkhtmltopdf()
    if wkhtml:
        try:
            config = pdfkit.configuration(wkhtmltopdf=wkhtml)
            # options utiles : gère la résolution CSS/IMG relative grâce à 'enable-local-file-access'
            options = {
                "enable-local-file-access": None,
                "quiet": "",
                "encoding": "UTF-8",
                # Ajoute d'autres options si besoin : marges, dpi, etc.
            }
            pdfkit.from_string(html, str(out_path), options=options, configuration=config)
            return out_path
        except Exception as e:
            # Log et fallback WeasyPrint
            import logging
            logging.getLogger(__name__).warning(
                "Échec wkhtmltopdf (%s). Fallback WeasyPrint...", e
            )

    # 3) Fallback WeasyPrint
    _render_pdf_with_weasyprint(html, out_path, base_url=base_url)
    return out_path
            quote={
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
                "siret": company.get("siret", ""),
            },
            terms=terms,
        )

        exports_dir = out_dir or os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "exports", "devis"))
        os.makedirs(exports_dir, exist_ok=True)
        base_name = f"{q.number or q.id}_devis ({client_name})"; base = os.path.join(exports_dir, base_name)
        pdf_path = base + ".pdf"

        # Try WeasyPrint first
        try:
            import weasyprint
            weasyprint.HTML(string=html, base_url=templates_dir).write_pdf(pdf_path, stylesheets=[weasyprint.CSS(os.path.join(templates_dir, "stylesheet.css"))])
            return pdf_path
        except Exception:
            pass

        # Fallback wkhtmltopdf via pdfkit
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
