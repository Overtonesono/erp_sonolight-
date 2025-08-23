from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit, QDialogButtonBox, QCheckBox, QLabel
)
from PySide6.QtCore import Qt
from typing import Optional

from core.models.product import Product
from core.models.service import Service


def _parse_price_eur_to_cent(txt: str) -> Optional[int]:
    if not txt:
        return None
    t = txt.strip().replace("€", "").replace(" ", "").replace(",", ".")
    try:
        euros = float(t)
    except ValueError:
        return None
    return int(round(euros * 100))


def _format_price_cent_to_eur(c: Optional[int]) -> str:
    if c is None:
        return ""
    return f"{c/100:.2f}"


class ProductServiceForm(QDialog):
    def __init__(self, parent=None, item=None, item_type: str = "product"):
        """
        item_type: "product" ou "service"
        item: Product ou Service existant (édition) ou None (création).
        """
        super().__init__(parent)
        self.setWindowTitle("Catalogue")
        self.setModal(True)
        self._item_type = item_type
        self._item_orig = item

        self.ed_ref = QLineEdit()
        self.ed_label = QLineEdit()
        self.ed_price = QLineEdit()
        self.ed_unit = QLineEdit()
        self.ed_desc = QTextEdit()
        self.cb_active = QCheckBox("Actif")

        form = QFormLayout()
        form.addRow("Référence (obligatoire)", self.ed_ref)
        form.addRow("Libellé (obligatoire)", self.ed_label)
        form.addRow("Prix TTC (€)", self.ed_price)
        form.addRow("Unité", self.ed_unit)
        form.addRow("Description", self.ed_desc)
        form.addRow("", self.cb_active)
        form.addRow("", QLabel("💡 Saisie du prix en euros (ex: 120 ou 120.00). Stockage interne en centimes."))

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)

        if item is not None:
            self._fill_from_item(item)

    def _fill_from_item(self, item):
        self.ed_ref.setText(item.ref or "")
        self.ed_label.setText(item.label or "")
        self.ed_price.setText(_format_price_cent_to_eur(item.price_ttc_cent))
        self.ed_unit.setText(item.unit or "")
        self.ed_desc.setPlainText(item.description or "")
        self.cb_active.setChecked(bool(item.active))

    def get_item(self):
        # validations minimum
        ref = self.ed_ref.text().strip()
        label = self.ed_label.text().strip()
        if not ref or not label:
            if not ref:
                self.ed_ref.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            elif not label:
                self.ed_label.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            return None

        price_cent = _parse_price_eur_to_cent(self.ed_price.text())
        if price_cent is None:
            price_cent = 0

        if self._item_orig:
            it = self._item_orig.model_copy(deep=True)
            it.ref = ref
            it.label = label
            it.description = self.ed_desc.toPlainText().strip() or None
            it.price_ttc_cent = price_cent
            it.unit = self.ed_unit.text().strip() or it.unit
            it.active = self.cb_active.isChecked()
            return it

        if self._item_type == "service":
            return Service(
                ref=ref, label=label,
                description=self.ed_desc.toPlainText().strip() or None,
                price_ttc_cent=price_cent,
                unit=self.ed_unit.text().strip() or "prestation",
                active=self.cb_active.isChecked(),
            )
        else:
            return Product(
                ref=ref, label=label,
                description=self.ed_desc.toPlainText().strip() or None,
                price_ttc_cent=price_cent,
                unit=self.ed_unit.text().strip() or "pièce",
                active=self.cb_active.isChecked(),
            )
