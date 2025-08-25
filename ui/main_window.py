from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QDialog
)
from PySide6.QtCore import Qt
import os

from PySide6.QtWidgets import QProgressBar
from core.services.client_service import ClientService
from core.services.catalog_service import CatalogService
from core.services.quote_service import QuoteService
from core.services.invoice_service import InvoiceService
from core.services.accounting_service import AccountingService
from core.models.quote import Quote
from ui.widgets.client_form import ClientForm
from ui.widgets.product_form import ProductServiceForm
from ui.widgets.quote_editor import QuoteEditor
from ui.widgets.payment_dialog import PaymentDialog
from core.services.workflow_service import WorkflowService
from core.services.calendar_service import CalendarService

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))

def money_cent_to_str(c: int) -> str:
    try: return f"{c/100:.2f} €".replace(".", ",")
    except: return "0,00 €"

def _ensure_eur_payload(it) -> dict:
    """
    Convertit l'objet retourné par ProductServiceForm en dict prêt pour CatalogService:
    - garde id/ref/name/label/description/unit/active
    - si it.price_eur existe => l'utilise
    - sinon si it.price_cents existe => convertit en euros
    - sinon laisse à 0.0
    """
    def _get(o, name, default=None):
        return getattr(o, name, o.get(name, default)) if isinstance(o, dict) else getattr(o, name, default)

    payload = {
        "id": _get(it, "id"),
        "ref": _get(it, "ref"),
        "name": _get(it, "name", "") or _get(it, "label", ""),
        "label": _get(it, "label"),
        "description": _get(it, "description"),
        "unit": _get(it, "unit", ""),
        "active": bool(_get(it, "active", True)),
    }
    if hasattr(it, "price_eur") or (isinstance(it, dict) and "price_eur" in it):
        val = _get(it, "price_eur", 0.0)
        try:
            payload["price_eur"] = float(str(val).replace(",", "."))
        except Exception:
            payload["price_eur"] = 0.0
    else:
        pc = _get(it, "price_cents", None)
        if pc is None:
            # tenter anciens champs
            pc = _get(it, "price_ttc_cent", _get(it, "price_ht_cent", _get(it, "price_cent", None)))
        try:
            payload["price_eur"] = round(float(pc or 0) / 100.0, 2)
        except Exception:
            payload["price_eur"] = 0.0
    return payload

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ERP Sonolight - Devis & Factures v1")
        self.resize(1280, 800)
        self.workflow = WorkflowService()
        self.calendar_service = CalendarService()

        self.client_service = ClientService()
        self.catalog_service = CatalogService()
        self.quote_service = QuoteService()
        self.invoice_service = InvoiceService()
        self.accounting_service = AccountingService()
        self.client_map = self.quote_service.load_client_map()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.tabs.addTab(self._clients_tab(), "Clients")
        self.tabs.addTab(self._catalog_tab(), "Catalogue")
        self.tabs.addTab(self._quotes_tab(), "Devis")
        self.tabs.addTab(self._accounting_tab(), "Comptabilité")
        self.tabs.addTab(self._settings_tab(), "Paramètres")

    # ==================== CLIENTS ====================
    def _clients_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)
        bar = QHBoxLayout()
        btn_new = QPushButton("Nouveau")
        btn_edit = QPushButton("Modifier")
        btn_del = QPushButton("Supprimer")
        btn_open_json = QPushButton("Ouvrir clients.json")
        bar.addWidget(btn_new); bar.addWidget(btn_edit); bar.addWidget(btn_del)
        bar.addStretch(1); bar.addWidget(btn_open_json)
        root.addLayout(bar)

        self.tbl_clients = QTableWidget(0, 6)
        self.tbl_clients.setHorizontalHeaderLabels(["Nom", "Contact", "Email", "Téléphone", "Ville", "ID"])
        self.tbl_clients.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_clients.setSelectionBehavior(self.tbl_clients.SelectionBehavior.SelectRows)
        self.tbl_clients.setEditTriggers(self.tbl_clients.EditTrigger.NoEditTriggers)
        root.addWidget(self.tbl_clients, 1)

        btn_new.clicked.connect(self._client_new)
        btn_edit.clicked.connect(self._client_edit)
        btn_del.clicked.connect(self._client_delete)
        btn_open_json.clicked.connect(lambda: QFileDialog.getOpenFileName(self, "Ouvrir clients.json", os.path.join(DATA_DIR, "clients.json")))

        self._refresh_clients()
        return w

    def _refresh_clients(self):
        items = self.client_service.list_clients()
        self.client_map = self.quote_service.load_client_map()
        self.tbl_clients.setRowCount(0)
        for c in items:
            r = self.tbl_clients.rowCount(); self.tbl_clients.insertRow(r)
            self.tbl_clients.setItem(r, 0, QTableWidgetItem(c.name or ""))
            self.tbl_clients.setItem(r, 1, QTableWidgetItem(c.contact_name or ""))
            self.tbl_clients.setItem(r, 2, QTableWidgetItem(c.email or ""))
            self.tbl_clients.setItem(r, 3, QTableWidgetItem(c.phone or ""))
            self.tbl_clients.setItem(r, 4, QTableWidgetItem((c.address.city if c.address else "") or ""))
            self.tbl_clients.setItem(r, 5, QTableWidgetItem(c.id))
        self.tbl_clients.resizeRowsToContents()

    def _selected_client_id(self):
        row = self.tbl_clients.currentRow()
        if row < 0: return None
        return self.tbl_clients.item(row, 5).text()

    def _client_new(self):
        dlg = ClientForm(self)
        if dlg.exec() == QDialog.Accepted:
            c = dlg.get_client()
            if not c:
                QMessageBox.warning(self, "Validation", "Nom obligatoire.")
                return
            self.client_service.add_client(c)
            self._refresh_clients()

    def _client_edit(self):
        cid = self._selected_client_id()
        if not cid:
            QMessageBox.information(self, "Clients", "Sélectionne une ligne d’abord.")
            return
        current = self.client_service.get_by_id(cid)
        if not current:
            QMessageBox.warning(self, "Clients", "Impossible de charger ce client.")
            return
        dlg = ClientForm(self, client=current)
        if dlg.exec() == QDialog.Accepted:
            c = dlg.get_client()
            if not c:
                QMessageBox.warning(self, "Validation", "Nom obligatoire.")
                return
            self.client_service.update_client(c)
            self._refresh_clients()

    def _client_delete(self):
        cid = self._selected_client_id()
        if not cid:
            QMessageBox.information(self, "Clients", "Sélectionne une ligne d’abord.")
            return
        if QMessageBox.question(self, "Suppression", "Supprimer ce client ?") == QMessageBox.Yes:
            self.client_service.delete_client(cid)
            self._refresh_clients()

    # ==================== CATALOGUE ====================
    def _catalog_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)

        # PRODUITS
        grp_p = QGroupBox("Produits"); lay_p = QVBoxLayout(grp_p)
        bar_p = QHBoxLayout()
        btn_p_new = QPushButton("Nouveau produit")
        btn_p_edit = QPushButton("Modifier")
        btn_p_del = QPushButton("Supprimer")
        btn_p_json = QPushButton("Ouvrir products.json")
        for b in (btn_p_new, btn_p_edit, btn_p_del): bar_p.addWidget(b)
        bar_p.addStretch(1); bar_p.addWidget(btn_p_json)
        lay_p.addLayout(bar_p)

        self.tbl_products = QTableWidget(0, 6)
        self.tbl_products.setHorizontalHeaderLabels(["Réf", "Libellé", "Prix TTC", "Unité", "Actif", "ID"])
        self.tbl_products.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_products.setSelectionBehavior(self.tbl_products.SelectionBehavior.SelectRows)
        self.tbl_products.setEditTriggers(self.tbl_products.EditTrigger.NoEditTriggers)
        lay_p.addWidget(self.tbl_products)

        # SERVICES
        grp_s = QGroupBox("Services"); lay_s = QVBoxLayout(grp_s)
        bar_s = QHBoxLayout()
        btn_s_new = QPushButton("Nouveau service")
        btn_s_edit = QPushButton("Modifier")
        btn_s_del = QPushButton("Supprimer")
        btn_s_json = QPushButton("Ouvrir services.json")
        for b in (btn_s_new, btn_s_edit, btn_s_del): bar_s.addWidget(b)
        bar_s.addStretch(1); bar_s.addWidget(btn_s_json)
        lay_s.addLayout(bar_s)

        self.tbl_services = QTableWidget(0, 6)
        self.tbl_services.setHorizontalHeaderLabels(["Réf", "Libellé", "Prix TTC", "Unité", "Actif", "ID"])
        self.tbl_services.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_services.setSelectionBehavior(self.tbl_services.SelectionBehavior.SelectRows)
        self.tbl_services.setEditTriggers(self.tbl_services.EditTrigger.NoEditTriggers)
        lay_s.addWidget(self.tbl_services)

        root.addWidget(grp_p); root.addWidget(grp_s)

        btn_p_new.clicked.connect(lambda: self._catalog_new("product"))
        btn_p_edit.clicked.connect(lambda: self._catalog_edit("product"))
        btn_p_del.clicked.connect(lambda: self._catalog_del("product"))
        btn_p_json.clicked.connect(lambda: QFileDialog.getOpenFileName(self, "Ouvrir products.json", os.path.join(DATA_DIR, "products.json")))
        btn_s_new.clicked.connect(lambda: self._catalog_new("service"))
        btn_s_edit.clicked.connect(lambda: self._catalog_edit("service"))
        btn_s_del.clicked.connect(lambda: self._catalog_del("service"))
        btn_s_json.clicked.connect(lambda: QFileDialog.getOpenFileName(self, "Ouvrir services.json", os.path.join(DATA_DIR, "services.json")))

        self._refresh_catalog()
        return w

    def _refresh_catalog(self):
        from core.services.catalog_service import CatalogService
        self.catalog_service = CatalogService()
        # Produits
        products = self.catalog_service.list_products()
        self.tbl_products.setRowCount(0)
        for p in products:
            r = self.tbl_products.rowCount(); self.tbl_products.insertRow(r)
            self.tbl_products.setItem(r, 0, QTableWidgetItem(p.ref or ""))
            self.tbl_products.setItem(r, 1, QTableWidgetItem(p.label or ""))
            self.tbl_products.setItem(r, 2, QTableWidgetItem(f"{p.price_eur:.2f} €".replace(".", ",")))
            self.tbl_products.setItem(r, 3, QTableWidgetItem(p.unit or ""))
            self.tbl_products.setItem(r, 4, QTableWidgetItem("Oui" if p.active else "Non"))
            self.tbl_products.setItem(r, 5, QTableWidgetItem(p.id))
        # Services
        services = self.catalog_service.list_services()
        self.tbl_services.setRowCount(0)
        for s in services:
            r = self.tbl_services.rowCount(); self.tbl_services.insertRow(r)
            self.tbl_services.setItem(r, 0, QTableWidgetItem(s.ref or ""))
            self.tbl_services.setItem(r, 1, QTableWidgetItem(s.label or ""))
            self.tbl_services.setItem(r, 2, QTableWidgetItem(f"{s.price_eur:.2f} €".replace(".", ",")))
            self.tbl_services.setItem(r, 3, QTableWidgetItem(s.unit or ""))
            self.tbl_services.setItem(r, 4, QTableWidgetItem("Oui" if s.active else "Non"))
            self.tbl_services.setItem(r, 5, QTableWidgetItem(s.id))
        self.tbl_products.resizeRowsToContents(); self.tbl_services.resizeRowsToContents()

    def _selected_catalog_id(self, which: str):
        if which == "product":
            row = self.tbl_products.currentRow()
            if row < 0: return None
            return self.tbl_products.item(row, 5).text()
        row = self.tbl_services.currentRow()
        if row < 0: return None
        return self.tbl_services.item(row, 5).text()

    def _catalog_new(self, which: str):
        dlg = ProductServiceForm(self, item=None, item_type=which)
        if dlg.exec() == QDialog.Accepted:
            it = dlg.get_item()
            if not it:
                QMessageBox.warning(self, "Validation", "Référence et libellé sont obligatoires.")
                return
            payload = _ensure_eur_payload(it)
            if which == "product":
                self.catalog_service.add_product(payload)  # type: ignore
            else:
                self.catalog_service.add_service(payload)  # type: ignore
            self._refresh_catalog()

    def _catalog_edit(self, which: str):
        iid = self._selected_catalog_id(which)
        if not iid:
            QMessageBox.information(self, "Catalogue", "Sélectionne une ligne d’abord.")
            return
        cur = self.catalog_service.get_product(iid) if which == "product" else self.catalog_service.get_service(iid)
        if not cur:
            QMessageBox.warning(self, "Catalogue", "Impossible de charger cet élément.")
            return
        dlg = ProductServiceForm(self, item=cur, item_type=which)
        if dlg.exec() == QDialog.Accepted:
            it = dlg.get_item()
            if not it:
                QMessageBox.warning(self, "Validation", "Référence et libellé sont obligatoires.")
                return
            payload = _ensure_eur_payload(it)
            if which == "product":
                self.catalog_service.update_product(payload)  # type: ignore
            else:
                self.catalog_service.update_service(payload)  # type: ignore
            self._refresh_catalog()

    def _catalog_del(self, which: str):
        iid = self._selected_catalog_id(which)
        if not iid:
            QMessageBox.information(self, "Catalogue", "Sélectionne une ligne d’abord.")
            return
        if QMessageBox.question(self, "Suppression", "Supprimer cet élément ?") == QMessageBox.Yes:
            if which == "product": self.catalog_service.delete_product(iid)
            else: self.catalog_service.delete_service(iid)
            self._refresh_catalog()

    # ==================== DEVIS + FACTURES ====================
    def _quotes_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)

        # Ligne 1: CRUD + PDF devis
        bar1 = QHBoxLayout()
        self.btn_new = QPushButton("Nouveau devis")
        self.btn_edit = QPushButton("Modifier")
        self.btn_del = QPushButton("Supprimer")
        self.btn_pdf = QPushButton("Générer PDF du devis")
        bar1.addWidget(self.btn_new); bar1.addWidget(self.btn_edit); bar1.addWidget(self.btn_del)
        bar1.addStretch(1); bar1.addWidget(self.btn_pdf)
        root.addLayout(bar1)

        # Ligne 2: Workflow ergonomique
        bar2 = QHBoxLayout()
        self.btn_refuse = QPushButton("Refuser devis")
        self.btn_pay_deposit = QPushButton("Enregistrer ACOMPTE (30%)")
        self.btn_pay_balance = QPushButton("Enregistrer SOLDE (70%)")
        self.btn_calendar = QPushButton("Créer évènement (Agenda)")
        bar2.addWidget(self.btn_calendar)
        self.btn_calendar.clicked.connect(self._quote_create_calendar_event)
        bar2.addWidget(self.btn_refuse); bar2.addStretch(1)
        bar2.addWidget(self.btn_pay_deposit); bar2.addWidget(self.btn_pay_balance)
        root.addLayout(bar2)

        # Progression + résumé montants
        bar3 = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.lbl_summary = QLabel("Total: 0,00 € | Payé: 0,00 € | Reste: 0,00 € | Évènement: –")
        bar3.addWidget(QLabel("Progression:"))
        bar3.addWidget(self.progress, 1)
        bar3.addWidget(self.lbl_summary)
        root.addLayout(bar3)

        # Table devis (7 colonnes, ID = col 6)
        self.tbl_quotes = QTableWidget(0, 7)
        self.tbl_quotes.setHorizontalHeaderLabels(["Numéro", "Client", "Statut", "Progress", "Total TTC", "Évènement", "ID"])
        self.tbl_quotes.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_quotes.setSelectionBehavior(self.tbl_quotes.SelectionBehavior.SelectRows)
        self.tbl_quotes.setEditTriggers(self.tbl_quotes.EditTrigger.NoEditTriggers)
        root.addWidget(self.tbl_quotes, 1)

        # Table factures liées
        self.tbl_invoices = QTableWidget(0, 6)
        self.tbl_invoices.setHorizontalHeaderLabels(["Numéro", "Type", "Statut", "Total TTC", "Créé le", "ID"])
        self.tbl_invoices.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_invoices.setSelectionBehavior(self.tbl_invoices.SelectionBehavior.SelectRows)
        self.tbl_invoices.setEditTriggers(self.tbl_invoices.EditTrigger.NoEditTriggers)
        root.addWidget(self.tbl_invoices, 1)

        # Tableau paiements
        self.tbl_payments = QTableWidget(0, 5)
        self.tbl_payments.setHorizontalHeaderLabels(["Date", "Type", "Montant TTC", "Moyen", "Facture liée"])
        self.tbl_payments.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_payments.setSelectionBehavior(self.tbl_payments.SelectionBehavior.SelectRows)
        self.tbl_payments.setEditTriggers(self.tbl_payments.EditTrigger.NoEditTriggers)
        root.addWidget(self.tbl_payments, 1)

        # Events
        self.btn_new.clicked.connect(self._quote_new)
        self.btn_edit.clicked.connect(self._quote_edit)
        self.btn_del.clicked.connect(self._quote_delete)
        self.btn_pdf.clicked.connect(self._quote_export_pdf)
        self.btn_refuse.clicked.connect(self._quote_refuse)
        self.btn_pay_deposit.clicked.connect(lambda: self._quote_record_payment(kind="ACOMPTE"))
        self.btn_pay_balance.clicked.connect(lambda: self._quote_record_payment(kind="SOLDE"))

        self.tbl_quotes.itemSelectionChanged.connect(self._on_quote_selection_changed)

        self._refresh_quotes()
        return w

    def _progress_value_for(self, q: Quote) -> int:
        if q.status == "REFUSED": return 0
        if q.status == "PENDING": return 25
        if q.status == "VALIDATED": return 60
        if q.status == "FINALIZED": return 100
        return 0

    def _apply_progress_style(self, q: Quote):
        # Barre colorée selon statut
        if q.status == "REFUSED":
            css = "QProgressBar::chunk{background:#d9534f;} QProgressBar{text-align:center;}"
        elif q.status == "FINALIZED":
            css = "QProgressBar::chunk{background:#5cb85c;} QProgressBar{text-align:center;}"
        elif q.status == "VALIDATED":
            css = "QProgressBar::chunk{background:#8bc34a;} QProgressBar{text-align:center;}"
        else:  # PENDING
            css = "QProgressBar::chunk{background:#bdbdbd;} QProgressBar{text-align:center;}"
        self.progress.setStyleSheet(css)

    # ---------- Résumé financiers ----------
    def _financial_summary_from_quote(self, q):
        """Retourne (total, paid, due) en centimes pour un devis."""
        q2 = self.quote_service.recalc_totals(q)
        qd = q2.model_dump() if hasattr(q2, "model_dump") else q2.__dict__
        total = int(qd.get("total_ttc_cent") or 0)
        paid = 0
        for p in qd.get("payments", []):
            try:
                paid += int(p.get("amount_cent"))
            except Exception:
                paid += int(getattr(p, "amount_cent", 0))
        due = max(0, total - paid)
        return total, paid, due

    def _update_summary_bar(self, q: Quote | None):
        if not q:
            self.progress.setValue(0)
            self.lbl_summary.setText("Total: 0,00 € | Payé: 0,00 € | Reste: 0,00 € | Évènement: –")
            return
        # Progress + style
        self.progress.setValue(self._progress_value_for(q))
        self._apply_progress_style(q)
        # Montants
        total, paid, due = self._financial_summary_from_quote(q)
        ev = q.event_date.isoformat() if q.event_date else "–"
        self.lbl_summary.setText(
            f"Total: {money_cent_to_str(total)} | Payé: {money_cent_to_str(paid)} | "
            f"Reste: {money_cent_to_str(due)} | Évènement: {ev}"
        )

    # ---------- Sélection devis ----------
    def _on_quote_selection_changed(self):
        self._refresh_invoices_for_selected_quote()
        self._refresh_payments_for_selected_quote()
        q = self._get_selected_quote_obj()
        self._update_summary_bar(q)

    def _selected_quote_id(self):
        row = self.tbl_quotes.currentRow()
        if row < 0: return None
        # ID = colonne 6 (cohérent avec l'entête à 7 colonnes)
        return self.tbl_quotes.item(row, 6).text()

    def _get_selected_quote_obj(self) -> Quote | None:
        qid = self._selected_quote_id()
        if not qid: return None
        return self.quote_service.get_by_id(qid)

    # ---------- Listes / refresh ----------
    def _refresh_quotes(self):
        self.client_map = self.quote_service.load_client_map()
        items = self.quote_service.list_quotes()
        self.tbl_quotes.setRowCount(0)
        for q in items:
            r = self.tbl_quotes.rowCount(); self.tbl_quotes.insertRow(r)
            self.tbl_quotes.setItem(r, 0, QTableWidgetItem(q.number or "—"))
            cname = self.client_map.get(q.client_id).name if self.client_map.get(q.client_id) else "?"
            self.tbl_quotes.setItem(r, 1, QTableWidgetItem(cname))
            self.tbl_quotes.setItem(r, 2, QTableWidgetItem(q.status))
            self.tbl_quotes.setItem(r, 3, QTableWidgetItem(f"{self._progress_value_for(q)}%"))
            self.tbl_quotes.setItem(r, 4, QTableWidgetItem(money_cent_to_str(q.total_ttc_cent)))
            self.tbl_quotes.setItem(r, 5, QTableWidgetItem(q.event_date.isoformat() if q.event_date else "—"))
            self.tbl_quotes.setItem(r, 6, QTableWidgetItem(q.id))
        self.tbl_quotes.resizeRowsToContents()
        # Maintient le résumé cohérent après refresh
        self._on_quote_selection_changed()

    def _refresh_invoices_for_selected_quote(self):
        qid = self._selected_quote_id()
        self.tbl_invoices.setRowCount(0)
        if not qid: return
        for inv in self.invoice_service.list_by_quote(qid):
            r = self.tbl_invoices.rowCount(); self.tbl_invoices.insertRow(r)
            self.tbl_invoices.setItem(r, 0, QTableWidgetItem(inv.number or "—"))
            self.tbl_invoices.setItem(r, 1, QTableWidgetItem(inv.type))
            self.tbl_invoices.setItem(r, 2, QTableWidgetItem(inv.status))
            self.tbl_invoices.setItem(r, 3, QTableWidgetItem(money_cent_to_str(inv.total_ttc_cent)))
            self.tbl_invoices.setItem(r, 4, QTableWidgetItem(inv.created_at.strftime("%Y-%m-%d")))
            self.tbl_invoices.setItem(r, 5, QTableWidgetItem(inv.id))
        self.tbl_invoices.resizeRowsToContents()

    def _refresh_payments_for_selected_quote(self):
        qid = self._selected_quote_id()
        self.tbl_payments.setRowCount(0)
        if not qid: return
        q = self.quote_service.get_by_id(qid)
        if not q: return
        for p in sorted(q.payments, key=lambda x: x.at):
            r = self.tbl_payments.rowCount(); self.tbl_payments.insertRow(r)
            self.tbl_payments.setItem(r, 0, QTableWidgetItem(p.at.strftime("%Y-%m-%d")))
            self.tbl_payments.setItem(r, 1, QTableWidgetItem(p.kind))
            self.tbl_payments.setItem(r, 2, QTableWidgetItem(money_cent_to_str(p.amount_cent)))
            self.tbl_payments.setItem(r, 3, QTableWidgetItem(p.method or "—"))
            self.tbl_payments.setItem(r, 4, QTableWidgetItem(p.invoice_id or "—"))
        self.tbl_payments.resizeRowsToContents()

    # ---------- Actions devis ----------
    def _quote_export_pdf(self):
        q = self._get_selected_quote_obj()
        if not q:
            QMessageBox.information(self, "Devis", "Sélectionne un devis."); return
        try:
            out = self.quote_service.export_quote_pdf(q)
            QMessageBox.information(self, "PDF devis", f"Fichier généré :\n{out}")
        except Exception as e:
            QMessageBox.critical(self, "PDF devis", str(e))

    def _quote_refuse(self):
        q = self._get_selected_quote_obj()
        if not q: QMessageBox.information(self, "Devis", "Sélectionne un devis."); return
        self.workflow.refuse_quote(q)
        self._refresh_quotes()  # met à jour liste + résumé

    def _quote_record_payment(self, kind: str):
        q = self._get_selected_quote_obj()
        if not q: QMessageBox.information(self, "Devis", "Sélectionne un devis."); return

        default_cent = int(round(q.total_ttc_cent * 0.30)) if kind == "ACOMPTE" else \
                       max(0, self._financial_summary_from_quote(q)[2])  # due actuel
        dlg = PaymentDialog(self, amount_cent=default_cent)
        if dlg.exec() != QDialog.Accepted:
            return
        method, amount_cent, paid_dt = dlg.get_payment()
        if amount_cent <= 0:
            QMessageBox.warning(self, "Paiement", "Montant invalide."); return

        if kind == "ACOMPTE":
            q, pdf_dep = self.workflow.record_deposit(q, amount_cent, method, paid_dt)
            msg = f"Acompte enregistré.\nPDF facture d'acompte :\n{pdf_dep}"
        else:
            q, pdf_solde, pdf_final = self.workflow.record_balance(q, amount_cent, method, paid_dt)
            msg = f"Solde enregistré.\nPDF facture de solde :\n{pdf_solde}"
            if pdf_final:
                msg += f"\nPDF facture finale :\n{pdf_final}"

        # Refresh global (liste + résumé + paiements)
        self._refresh_quotes()
        QMessageBox.information(self, "Encaissement", msg)

    # ---------- CRUD devis ----------
    def _quote_new(self):
        dlg = QuoteEditor(self, quote=None)
        if dlg.exec() == QDialog.Accepted:
            q = dlg.get_quote()
            if not q:
                QMessageBox.warning(self, "Validation", "Client obligatoire."); return
            self.quote_service.add_quote(q)
            self._refresh_quotes()  # met à jour résumé aussi

    def _quote_edit(self):
        q = self._get_selected_quote_obj()
        if not q:
            QMessageBox.information(self, "Devis", "Sélectionne un devis."); return
        dlg = QuoteEditor(self, quote=q)
        if dlg.exec() == QDialog.Accepted:
            q2 = dlg.get_quote()
            if not q2:
                QMessageBox.warning(self, "Validation", "Client obligatoire."); return
            self.quote_service.update_quote(q2)
            self._refresh_quotes()  # met à jour résumé aussi

    def _quote_delete(self):
        qid = self._selected_quote_id()
        if not qid:
            QMessageBox.information(self, "Devis", "Sélectionne un devis."); return
        if QMessageBox.question(self, "Suppression", "Supprimer ce devis ?") == QMessageBox.Yes:
            self.quote_service.delete_quote(qid)
            self._refresh_quotes()

    # ---------- Agenda ----------
    def _quote_create_calendar_event(self):
        q = self._get_selected_quote_obj()
        if not q:
            QMessageBox.information(self, "Agenda", "Sélectionne un devis."); return
        if not q.event_date:
            QMessageBox.warning(self, "Agenda", "Ce devis n'a pas de date d'évènement."); return
        client = self.client_map.get(q.client_id)
        title = f"Prestation – {client.name if client else 'Client'} – {q.number}"
        desc = f"Devis {q.number}. Total: {q.total_ttc_cent/100:.2f} €".replace(".", ",")
        try:
            msg = self.calendar_service.create_event_for_quote(title=title, date_only=q.event_date, description=desc)
            QMessageBox.information(self, "Agenda", msg)
        except Exception as e:
            QMessageBox.warning(self, "Agenda", str(e))

    # ==================== COMPTA / PARAMS ====================
    def _accounting_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        path = os.path.join(DATA_DIR, "accounting_entries.json")
        lay.addWidget(QLabel(f"Écritures comptables – JSON: {path}"))
        return w

    def _settings_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        path = os.path.join(DATA_DIR, "settings.json")
        lay.addWidget(QLabel(f"Paramètres: {path}"))
        btn_open = QPushButton("Ouvrir dossier data…")
        btn_open.clicked.connect(lambda: QFileDialog.getOpenFileName(self, "Ouvrir un fichier", DATA_DIR))
        lay.addWidget(btn_open)
        return w
