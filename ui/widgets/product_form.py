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
    def __init__(self, parent=None, item: Optional[object] = None, item_type: str = "product"):
        super().__init__(parent)
        self.setWindowTitle("Produit/Service")
        self.setModal(True)
        self.item_type = item_type
        
        
        self.ed_ref = QLineEdit()
        self.ed_label = QLineEdit()
        self.ed_price = QLineEdit()
        self.ed_unit = QLineEdit()
        self.cb_active = QCheckBox("Actif")
        self.cb_active.setChecked(True)
        # ✨ Nouveau
        self.ed_desc = QTextEdit()
        self.ed_desc.setPlaceholderText("Description détaillée pour le devis/facture…")
        
        
        form = QFormLayout()
        form.addRow("Référence", self.ed_ref)
        form.addRow("Libellé", self.ed_label)
        form.addRow("Prix TTC (centimes)", self.ed_price)
        form.addRow("Unité", self.ed_unit)
        form.addRow("Description", self.ed_desc)
        form.addRow("", self.cb_active)
        
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        
        
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)
        
        
        # Remplissage si édition
        if item is not None:
            self.ed_ref.setText(getattr(item, "ref", ""))
            self.ed_label.setText(getattr(item, "label", ""))
            self.ed_price.setText(str(getattr(item, "price_ttc_cent", 0)))
            self.ed_unit.setText(getattr(item, "unit", ""))
            self.cb_active.setChecked(bool(getattr(item, "active", True)))
            self.ed_desc.setPlainText(getattr(item, "description", "") or "")
    
    
    def get_item(self) -> Optional[object]:
        try:
            price_cent = int(self.ed_price.text().strip() or 0)
        except ValueError:
            price_cent = 0
        data = dict(
            ref=self.ed_ref.text().strip(),
            label=self.ed_label.text().strip(),
            price_ttc_cent=price_cent,
            unit=self.ed_unit.text().strip() or ("heure" if self.item_type == "service" else "unité"),
            active=self.cb_active.isChecked(),
            description=(self.ed_desc.toPlainText().strip() or None),
        )
        if not data["ref"] or not data["label"]:
            return None
        if self.item_type == "service":
            return Service(**data)
        return Product(**data)
