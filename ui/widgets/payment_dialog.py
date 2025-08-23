from __future__ import annotations
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QComboBox, QDoubleSpinBox, QDialogButtonBox
from PySide6.QtCore import QDate
from typing import Optional

class PaymentDialog(QDialog):
    def __init__(self, parent=None, amount_cent: int = 0):
        super().__init__(parent)
        self.setWindowTitle("Encaissement")
        self.setModal(True)

        self.cb_method = QComboBox()
        self.cb_method.addItems(["CB", "VIREMENT", "ESPECES", "CHEQUE", "AUTRE"])

        self.sp_amount = QDoubleSpinBox()
        self.sp_amount.setRange(0, 1e12)
        self.sp_amount.setDecimals(2)
        self.sp_amount.setValue(amount_cent / 100.0)

        form = QFormLayout()
        form.addRow("Moyen de paiement", self.cb_method)
        form.addRow("Montant TTC (€)", self.sp_amount)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)

    def get_payment(self) -> Optional[tuple[str, int]]:
        method = self.cb_method.currentText()
        amount_cent = int(round(float(self.sp_amount.value()) * 100))
        return method, amount_cent
