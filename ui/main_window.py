from PySide6.QtWidgets import (
        QMainWindow, QWidget, QTabWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt
import json, os

    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "data")
    DATA_DIR = os.path.abspath(DATA_DIR)

    def _load_json(name):
        path = os.path.join(DATA_DIR, name)
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return []

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("ERP Sonolight - MVP")
            self.resize(1100, 700)

            self.tabs = QTabWidget()
            self.setCentralWidget(self.tabs)

            self.tabs.addTab(self._clients_tab(), "Clients")
            self.tabs.addTab(self._catalog_tab(), "Catalogue")
            self.tabs.addTab(self._quotes_tab(), "Devis")
            self.tabs.addTab(self._accounting_tab(), "Comptabilité")
            self.tabs.addTab(self._settings_tab(), "Paramètres")

        def _clients_tab(self):
            w = QWidget(); lay = QVBoxLayout(w)
            nb = len(_load_json("clients.json"))
            lay.addWidget(QLabel(f"Clients chargés: {nb}"))
            btn = QPushButton("Ouvrir le dossier des données…")
            btn.clicked.connect(lambda: QFileDialog.getOpenFileName(self, "Ouvrir clients.json", os.path.join(DATA_DIR, "clients.json")))
            lay.addWidget(btn)
            tip = QLabel("💡 MVP: la gestion CRUD arrivEra dans la prochaine itération.
"
                         "Pour tester, édite data/clients.json à la main.")
            tip.setWordWrap(True); lay.addWidget(tip, 1, alignment=Qt.AlignTop)
            return w

        def _catalog_tab(self):
            w = QWidget(); lay = QVBoxLayout(w)
            products = len(_load_json("products.json"))
            services = len(_load_json("services.json"))
            lay.addWidget(QLabel(f"Produits: {products}  |  Services: {services}"))
            lay.addWidget(QLabel("MVP: Ajout/édition via JSON pour l'instant."))
            return w

        def _quotes_tab(self):
            w = QWidget(); lay = QVBoxLayout(w)
            quotes = len(_load_json("quotes.json"))
            btn_pdf = QPushButton("Exporter un devis en PDF (fictif)")
            btn_pdf.clicked.connect(self._fake_pdf)
            lay.addWidget(QLabel(f"Devis: {quotes}"))
            lay.addWidget(btn_pdf)
            lay.addWidget(QLabel("MVP: Workflow devis/factures et Google Agenda arrivent ensuite."))
            return w

        def _accounting_tab(self):
            w = QWidget(); lay = QVBoxLayout(w)
            n = len(_load_json("accounting_entries.json"))
            lay.addWidget(QLabel(f"Ecritures comptables: {n}"))
            lay.addWidget(QLabel("Export CSV à venir."))
            return w

        def _settings_tab(self):
            w = QWidget(); lay = QVBoxLayout(w)
            settings_path = os.path.join(DATA_DIR, "settings.json")
            lay.addWidget(QLabel(f"Paramètres: {settings_path}"))
            lay.addWidget(QLabel("MVP: edition via JSON; connexion Google dans une prochaine itération."))
            return w

        def _fake_pdf(self):
            QMessageBox.information(self, "PDF", "La génération PDF sera branchée sur les templates HTML.
(MVP placeholder)")
