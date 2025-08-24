from __future__ import annotations
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QCheckBox, QPushButton, QWidget, QLabel, QComboBox
)


def _get(obj: Any, name: str, default=None):
    """Accès souple attribut/dict."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _to_float_eur(text: str) -> float:
    if not text:
        return 0.0
    t = text.replace("€", "").replace(" ", "").replace(",", ".")
    try:
        return round(float(t), 2)
    except Exception:
        return 0.0


class ProductServiceForm(QDialog):
    """
    Formulaire unique pour Produit / Service.
    - Edition du prix en EUROS (price_eur), pas en centimes.
    - Retourne un dict prêt pour CatalogService (id/ref/name/label/description/unit/active/price_eur).
    """
    def __init__(self, parent: Optional[QWidget] = None, item: Optional[Any] = None, item_type: str = "product"):
        super().__init__(parent)
        self.setWindowTitle("Édition " + ("Produit" if item_type == "product" else "Service"))
        self.item_type = item_type
        self.item = item

        # Widgets
        self.ed_ref = QLineEdit()
        self.ed_label = QLineEdit()
        self.ed_name = QLineEdit()  # masqué mais utile si tu veux distinguer label/name plus tard
        self.ed_desc = QTextEdit()
        self.ed_unit = QLineEdit()
        self.cb_active = QCheckBox("Actif")
        self.ed_price_eur = QLineEdit()
        self.ed_price_eur.setPlaceholderText("ex: 18,50")

        # Pré-remplissage
        self._populate_from_item(item)

        # Layout
        form = QFormLayout()
        form.addRow("Référence*", self.ed_ref)
        form.addRow("Libellé*", self.ed_label)
        form.addRow("Prix TTC (€)*", self.ed_price_eur)
        form.addRow("Unité", self.ed_unit)
        form.addRow("Actif", self.cb_active)
        form.addRow("Description", self.ed_desc)

        # Boutons
        btn_ok = QPushButton("Valider")
        btn_cancel = QPushButton("Annuler")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        bar = QHBoxLayout()
        bar.addStretch(1)
        bar.addWidget(btn_cancel)
        bar.addWidget(btn_ok)

        root = QVBoxLayout(self)
        root.addLayout(form)
        root.addLayout(bar)

        # UX: ENTER valide
        self.ed_ref.returnPressed.connect(btn_ok.click)
        self.ed_label.returnPressed.connect(btn_ok.click)
        self.ed_price_eur.returnPressed.connect(btn_ok.click)
        self.resize(520, 420)

    # ------------------ Helpers ------------------ #

    def _populate_from_item(self, item: Optional[Any]) -> None:
        """Remplit le formulaire depuis l'objet (Product/Service ou dict)."""
        self.ed_ref.setText(_get(item, "ref", "") or "")
        # Priorité label ; sinon fallback name
        label = _get(item, "label", "") or _get(item, "name", "")
        self.ed_label.setText(label or "")
        self.ed_name.setText(_get(item, "name", label) or "")
        self.ed_desc.setPlainText(_get(item, "description", "") or "")
        self.ed_unit.setText(_get(item, "unit", "") or "")
        self.cb_active.setChecked(bool(_get(item, "active", True)))

        # Prix en euros: si l'objet expose price_eur -> utiliser ; sinon convertir depuis centimes/anciens champs.
        if _get(item, "price_eur", None) is not None:
            eur = float(_get(item, "price_eur", 0.0))
        else:
            # reconstitution depuis centimes si nécessaire
            raw_cent = (
                _get(item, "price_cents", None)
                or _get(item, "price_ttc_cent", None)
                or _get(item, "price_ht_cent", None)
                or _get(item, "price_cent", None)
                or 0
            )
            try:
                eur = round(float(raw_cent) / 100.0, 2)
            except Exception:
                eur = 0.0
        self.ed_price_eur.setText(f"{eur:.2f}")

    # ------------------ API ------------------ #

    def get_item(self) -> Optional[Dict[str, Any]]:
        """Retourne un dict prêt pour CatalogService (utilise price_eur)."""
        ref = self.ed_ref.text().strip()
        label = self.ed_label.text().strip()
        if not ref or not label:
            return None

        eur = _to_float_eur(self.ed_price_eur.text())
        payload: Dict[str, Any] = {
            "id": _get(self.item, "id"),  # conserve l'id en édition
            "ref": ref,
            "label": label,
            "name": self.ed_name.text().strip() or label,  # garde name cohérent si utilisé ailleurs
            "description": self.ed_desc.toPlainText().strip() or None,
            "unit": self.ed_unit.text().strip(),
            "active": self.cb_active.isChecked(),
            "price_eur": eur,  # <-- CLÉ IMPORTANTE (le service convertira en centimes)
            # hint item_type si tu l’utilises en aval
            "type": self.item_type,
        }
        return payload
