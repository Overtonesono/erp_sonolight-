from __future__ import annotations
from typing import Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QTextEdit, QDialogButtonBox,
    QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QDoubleSpinBox, QLabel, QDateEdit
)
from PySide6.QtCore import Qt, QDate

from core.models.quote import Quote, QuoteLine
from core.services.quote_service import QuoteService
from core.services.catalog_service import CatalogService
from core.services.client_service import ClientService


def _money(c: int) -> str:
    return f"{c/100:.2f} €"


class _AddLineDialog(QDialog):
    """Sélecteur simple pour ajouter un produit/service."""
    def __init__(self, parent=None, catalog: CatalogService | None = None):
        super().__init__(parent)
        self.setWindowTitle("Ajouter une ligne")
        self.setModal(True)
        self.catalog = catalog or CatalogService()

        self.cb_type = QComboBox()
        self.cb_type.addItems(["service", "product"])
        self.cb_item = QComboBox()
        self.sp_qty = QDoubleSpinBox(); self.sp_qty.setRange(0.0, 1e6); self.sp_qty.setDecimals(2); self.sp_qty.setValue(1.0)
        self.sp_discount = QDoubleSpinBox(); self.sp_discount.setRange(0.0, 100.0); self.sp_discount.setSuffix(" %")
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        form = QFormLayout()
        form.addRow("Type", self.cb_type)
        form.addRow("Article", self.cb_item)
        form.addRow("Quantité", self.sp_qty)
        form.addRow("Remise", self.sp_discount)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)

        self.cb_type.currentTextChanged.connect(self._refresh_items)
        self._refresh_items()

        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

    def _refresh_items(self):
        self.cb_item.clear()
        if self.cb_type.currentText() == "product":
            for p in self.catalog.list_products():
                self.cb_item.addItem(f"{p.ref} — {p.label} ({_money(p.price_ttc_cent)})", ("product", p.id, p.label, p.price_ttc_cent))
        else:
            for s in self.catalog.list_services():
                self.cb_item.addItem(f"{s.ref} — {s.label} ({_money(s.price_ttc_cent)})", ("service", s.id, s.label, s.price_ttc_cent))

    def get_line(self) -> Optional[QuoteLine]:
        data = self.cb_item.currentData()
        if not data:
            return None
        typ, item_id, label, price_cent = data
        q = float(self.sp_qty.value())
        d = float(self.sp_discount.value())
        return QuoteLine(
            item_id=item_id, item_type=typ, label=label, qty=q,
            unit_price_ttc_cent=int(price_cent), remise_pct=d
        )


class QuoteEditor(QDialog):
    def __init__(self, parent=None, quote: Optional[Quote] = None):
        super().__init__(parent)
        self.setWindowTitle("Devis")
        self.setModal(True)
        self.service = QuoteService()
        self.client_service = ClientService()
        self.catalog_service = CatalogService()
                
        self.cb_client = QComboBox()
        self.ed_notes = QTextEdit()
        self.ed_event_date = QDateEdit(); self.ed_event_date.setCalendarPopup(True); self.ed_event_date.setDate(QDate.currentDate())
                
        self.lab_total = QLabel("Total TTC : 0.00 €")
                
        # ✨ Ajout colonne Description
        self.tbl = QTableWidget(0, 7)
        self.tbl.setHorizontalHeaderLabels(["Type", "Libellé", "Description", "Qté", "PU TTC", "Remise %", "Total TTC"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setSelectionBehavior(self.tbl.SelectionBehavior.SelectRows)
        self.tbl.setEditTriggers(self.tbl.EditTrigger.NoEditTriggers)
                
        btn_add = QPushButton("Ajouter une ligne")
        btn_del = QPushButton("Supprimer la ligne")
        btn_add.clicked.connect(self._add_line)
        btn_del.clicked.connect(self._del_line)
                
        top = QFormLayout()
        top.addRow("Client", self.cb_client)
        top.addRow("Date de l’évènement", self.ed_event_date)
        top.addRow("Notes", self.ed_notes)
                
        bar = QHBoxLayout()
        bar.addWidget(btn_add); bar.addWidget(btn_del); bar.addStretch(1); bar.addWidget(self.lab_total)
                
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
                
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(bar)
        lay.addWidget(self.tbl)
        lay.addWidget(btns)
                
        self._quote_orig = quote
        self._lines: list[QuoteLine] = []
        self._clients = self.service.load_client_map()
        for cid, c in self._clients.items():
            self.cb_client.addItem(f"{c.name} ({c.email or '—'})", cid)
                
        if quote:
            self._fill_from_quote(quote)
        else:
            self._update_totals()

    # -------- UI helpers --------
    def _fill_from_quote(self, q: Quote):
        # client
        idx = max(0, self.cb_client.findData(q.client_id))
        self.cb_client.setCurrentIndex(idx)
        self.ed_notes.setPlainText(q.notes or "")
        if q.event_date:
            self.ed_event_date.setDate(QDate(q.event_date.year, q.event_date.month, q.event_date.day))
        # lignes
        self._lines = [ln.model_copy(deep=True) for ln in q.lines]
        self._refresh_table()

    def _refresh_table(self):
        self.tbl.setRowCount(0)
        qtmp = Quote(client_id=self.cb_client.currentData() or "", lines=[ln.model_copy(deep=True) for ln in self._lines])
        self.service.recalc_totals(qtmp)
        for ln in qtmp.lines:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            self.tbl.setItem(r, 0, QTableWidgetItem(ln.item_type))
            self.tbl.setItem(r, 1, QTableWidgetItem(ln.label))
            self.tbl.setItem(r, 2, QTableWidgetItem(f"{ln.qty:g}"))
            self.tbl.setItem(r, 3, QTableWidgetItem(_money(ln.unit_price_ttc_cent)))
            self.tbl.setItem(r, 4, QTableWidgetItem(f"{ln.remise_pct:.0f}"))
            self.tbl.setItem(r, 5, QTableWidgetItem(_money(ln.total_line_ttc_cent)))
        self.tbl.resizeRowsToContents()
        self._update_totals()

    def _update_totals(self):
        qtmp = Quote(client_id=self.cb_client.currentData() or "", lines=[ln.model_copy(deep=True) for ln in self._lines])
        self.service.recalc_totals(qtmp)
        self.lab_total.setText(f"Total TTC : {_money(qtmp.total_ttc_cent)}")

    def _add_line(self):
        dlg = _AddLineDialog(self, self.catalog_service)
        if dlg.exec() == QDialog.Accepted:
            ln = dlg.get_line()
            if ln:
                self._lines.append(ln)
                self._refresh_table()

    def _del_line(self):
        row = self.tbl.currentRow()
        if row < 0: return
        del self._lines[row]
        self._refresh_table()

    # -------- Result --------
    def get_quote(self) -> Optional[Quote]:
        client_id = self.cb_client.currentData()
        if not client_id:
            return None

        event_qdate = self.ed_event_date.date()
        event_date = event_qdate.toPython()  # datetime.date

        if self._quote_orig:
            q = self._quote_orig.model_copy(deep=True)
            q.client_id = client_id
            q.notes = self.ed_notes.toPlainText().strip() or None
            q.lines = [ln.model_copy(deep=True) for ln in self._lines]
            q.event_date = event_date
            self.service.recalc_totals(q)
            return q

        qnew = Quote(
            client_id=client_id,
            lines=[ln.model_copy(deep=True) for ln in self._lines],
            notes=self.ed_notes.toPlainText().strip() or None,
            event_date=event_date
        )
        self.service.recalc_totals(qnew)
        return qnew
