from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime, date
from .common import gen_id

QuoteStatus = Literal["PENDING", "VALIDATED", "FINALIZED", "REFUSED"]

class QuoteLine(BaseModel):
    item_id: Optional[str] = None
    item_type: Literal["product", "service"] = "service"
    label: str
    qty: float = 1.0
    unit_price_ttc_cent: int = 0
    remise_pct: float = 0.0
    total_line_ttc_cent: int = 0

class PaymentRecord(BaseModel):
    id: str = Field(default_factory=gen_id)
    kind: Literal["ACOMPTE", "SOLDE"] = "ACOMPTE"
    amount_cent: int
    method: Optional[str] = None   # CB, VIREMENT, etc.
    at: datetime = Field(default_factory=datetime.utcnow)  # date/heure paiement
    invoice_id: Optional[str] = None  # facture liée (si générée)

class Quote(BaseModel):
    id: str = Field(default_factory=gen_id)
    number: Optional[str] = None
    client_id: str
    status: QuoteStatus = "PENDING"

    created_at: datetime = Field(default_factory=datetime.utcnow)
    decided_at: Optional[datetime] = None

    # ✨ NOUVEAU : date de l’évènement
    event_date: Optional[date] = None

    lines: List[QuoteLine] = Field(default_factory=list)
    total_ttc_cent: int = 0

    # ✨ Paiements stockés au niveau du devis (master)
    payments: List[PaymentRecord] = Field(default_factory=list)
    notes: Optional[str] = None

    # helpers
    def paid_deposit_cent(self) -> int:
        return sum(p.amount_cent for p in self.payments if p.kind == "ACOMPTE")

    def paid_balance_cent(self) -> int:
        return sum(p.amount_cent for p in self.payments if p.kind == "SOLDE")

    def paid_total_cent(self) -> int:
        return self.paid_deposit_cent() + self.paid_balance_cent()

    def remaining_cent(self) -> int:
        return max(0, self.total_ttc_cent - self.paid_total_cent())
