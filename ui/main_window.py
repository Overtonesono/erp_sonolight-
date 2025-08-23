from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox, QDialog   # <-- ajouté
)
from PySide6.QtCore import Qt
import os

from core.services.client_service import ClientService
from core.services.catalog_service import CatalogService
from core.services.quote_service import QuoteService
from core.models.client import Client
from core.models.product import Product
from core.models.service import Service
from core.models.quote import Quote

from ui.widgets.client_form import ClientForm
from ui.widgets.product_form import ProductServiceForm
from ui.widgets.quote_editor import QuoteEditor


DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))

def money_cent_to_str(c: int) -> str:
    try: return f"{c/100:.2f} €"
    except: return "0.00 €"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ERP Sonolight - CRUD + Devis v1")
        self.resize(1280, 800)

        self.client_service = ClientService()
        self.catalog_service = CatalogService()
        self.quote_service = QuoteService()
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
            self.tbl_products.setItem(r, 2, QTableWidgetItem(money_cent_to_str(p.price_ttc_cent)))
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
            self.tbl_services.setItem(r, 2, QTableWidgetItem(money_cent_to_str(s.price_ttc_cent)))
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
            if which == "product": self.catalog_service.add_product(it)  # type: ignore
            else: self.catalog_service.add_service(it)  # type: ignore
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
            if which == "product": self.catalog_service.update_product(it)  # type: ignore
            else: self.catalog_service.update_service(it)  # type: ignore
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

    # ==================== DEVIS ====================
    def _quotes_tab(self):
        w = QWidget()
        root = QVBoxLayout(w)

        bar = QHBoxLayout()
        btn_new = QPushButton("Nouveau devis")
        btn_edit = QPushButton("Modifier")
        btn_del = QPushButton("Supprimer")
        btn_pdf = QPushButton("Exporter PDF/HTML")
        for b in (btn_new, btn_edit, btn_del): bar.addWidget(b)
        bar.addStretch(1); bar.addWidget(btn_pdf)
        root.addLayout(bar)

        self.tbl_quotes = QTableWidget(0, 6)
        self.tbl_quotes.setHorizontalHeaderLabels(["Numéro", "Client", "Statut", "Total TTC", "Créé le", "ID"])
        self.tbl_quotes.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_quotes.setSelectionBehavior(self.tbl_quotes.SelectionBehavior.SelectRows)
        self.tbl_quotes.setEditTriggers(self.tbl_quotes.EditTrigger.NoEditTriggers)
        root.addWidget(self.tbl_quotes, 1)

        btn_new.clicked.connect(self._quote_new)
        btn_edit.clicked.connect(self._quote_edit)
        btn_del.clicked.connect(self._quote_delete)
        btn_pdf.clicked.connect(self._quote_export)

        self._refresh_quotes()
        return w

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
            self.tbl_quotes.setItem(r, 3, QTableWidgetItem(money_cent_to_str(q.total_ttc_cent)))
            self.tbl_quotes.setItem(r, 4, QTableWidgetItem(q.created_at.strftime("%Y-%m-%d")))
            self.tbl_quotes.setItem(r, 5, QTableWidgetItem(q.id))
        self.tbl_quotes.resizeRowsToContents()

    def _selected_quote_id(self):
        row = self.tbl_quotes.currentRow()
        if row < 0: return None
        return self.tbl_quotes.item(row, 5).text()

    def _quote_new(self):
        dlg = QuoteEditor(self, quote=None)
        if dlg.exec() == QDialog.Accepted:
            q = dlg.get_quote()
            if not q:
                QMessageBox.warning(self, "Validation", "Client obligatoire.")
                return
            self.quote_service.add_quote(q)
            self._refresh_quotes()

    def _quote_edit(self):
        qid = self._selected_quote_id()
        if not qid:
            QMessageBox.information(self, "Devis", "Sélectionne une ligne d’abord.")
            return
        cur = self.quote_service.get_by_id(qid)
        if not cur:
            QMessageBox.warning(self, "Devis", "Impossible de charger ce devis.")
            return
        dlg = QuoteEditor(self, quote=cur)
        if dlg.exec() == QDialog.Accepted:
            q = dlg.get_quote()
            if not q:
                QMessageBox.warning(self, "Validation", "Client obligatoire.")
                return
            self.quote_service.update_quote(q)
            self._refresh_quotes()

    def _quote_delete(self):
        qid = self._selected_quote_id()
        if not qid:
            QMessageBox.information(self, "Devis", "Sélectionne une ligne d’abord.")
            return
        if QMessageBox.question(self, "Suppression", "Supprimer ce devis ?") == QMessageBox.Yes:
            self.quote_service.delete_quote(qid)
            self._refresh_quotes()

    def _quote_export(self):
        qid = self._selected_quote_id()
        if not qid:
            QMessageBox.information(self, "Devis", "Sélectionne une ligne d’abord.")
            return
        cur = self.quote_service.get_by_id(qid)
        if not cur:
            QMessageBox.warning(self, "Devis", "Impossible de charger ce devis.")
            return
        out_path = self.quote_service.export_quote_pdf(cur)
        QMessageBox.information(self, "Export", f"Fichier généré :\n{out_path}")

    # ==================== COMPTA ====================
    def _accounting_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        accounting_path = os.path.join(DATA_DIR, "accounting_entries.json")
        lay.addWidget(QLabel(f"Écritures comptables – JSON: {accounting_path}"))
        lay.addWidget(QLabel("Étapes suivantes : écritures auto + export CSV."))
        return w

    # ==================== PARAMÈTRES ====================
    def _settings_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        settings_path = os.path.join(DATA_DIR, "settings.json")
        lay.addWidget(QLabel(f"Paramètres: {settings_path}"))
        btn_open = QPushButton("Ouvrir dossier data…")
        btn_open.clicked.connect(lambda: QFileDialog.getOpenFileName(self, "Ouvrir un fichier", DATA_DIR))
        lay.addWidget(btn_open)
        lay.addWidget(QLabel("À venir : connexion Google + préférences Agenda."))
        return w
