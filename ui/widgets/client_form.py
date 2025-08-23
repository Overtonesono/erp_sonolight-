from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit, QDialogButtonBox
)
from PySide6.QtCore import Qt
from typing import Optional

from core.models.client import Client, Address


class ClientForm(QDialog):
    def __init__(self, parent=None, client: Optional[Client] = None):
        super().__init__(parent)
        self.setWindowTitle("Client")
        self.setModal(True)

        self.ed_name = QLineEdit()
        self.ed_contact = QLineEdit()
        self.ed_email = QLineEdit()
        self.ed_phone = QLineEdit()
        self.ed_addr1 = QLineEdit()
        self.ed_addr2 = QLineEdit()
        self.ed_cp = QLineEdit()
        self.ed_city = QLineEdit()
        self.ed_notes = QTextEdit()

        form = QFormLayout()
        form.addRow("Nom (obligatoire)", self.ed_name)
        form.addRow("Contact", self.ed_contact)
        form.addRow("Email", self.ed_email)
        form.addRow("Téléphone", self.ed_phone)
        form.addRow("Adresse ligne 1", self.ed_addr1)
        form.addRow("Adresse ligne 2", self.ed_addr2)
        form.addRow("Code postal", self.ed_cp)
        form.addRow("Ville", self.ed_city)
        form.addRow("Notes", self.ed_notes)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)

        self._orig_client = client
        if client:
            self._fill_from_client(client)

    def _fill_from_client(self, c: Client):
        self.ed_name.setText(c.name or "")
        self.ed_contact.setText(c.contact_name or "")
        self.ed_email.setText(c.email or "")
        self.ed_phone.setText(c.phone or "")
        if c.address:
            self.ed_addr1.setText(c.address.line1 or "")
            self.ed_addr2.setText(c.address.line2 or "")
            self.ed_cp.setText(c.address.postal_code or "")
            self.ed_city.setText(c.address.city or "")
        self.ed_notes.setPlainText(c.notes or "")

    def get_client(self) -> Optional[Client]:
        """Retourne un Client (nouveau ou mis à jour) ou None si invalide."""
        name = self.ed_name.text().strip()
        if not name:
            self.ed_name.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
            return None

        addr = None
        if self.ed_addr1.text().strip() or self.ed_cp.text().strip() or self.ed_city.text().strip():
            addr = Address(
                line1=self.ed_addr1.text().strip(),
                line2=self.ed_addr2.text().strip() or None,
                postal_code=self.ed_cp.text().strip(),
                city=self.ed_city.text().strip(),
            )

        if self._orig_client:
            # update in place
            c = self._orig_client.model_copy(deep=True)
            c.name = name
            c.contact_name = self.ed_contact.text().strip() or None
            c.email = (self.ed_email.text().strip() or None)
            c.phone = (self.ed_phone.text().strip() or None)
            c.address = addr
            c.notes = self.ed_notes.toPlainText().strip() or None
            return c

        # new
        return Client(
            name=name,
            contact_name=self.ed_contact.text().strip() or None,
            email=(self.ed_email.text().strip() or None),
            phone=(self.ed_phone.text().strip() or None),
            address=addr,
            notes=self.ed_notes.toPlainText().strip() or None,
        )
