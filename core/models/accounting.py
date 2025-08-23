from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime
from .common import gen_id

EntryType = Literal["ACOMPTE", "SOLDE", "VENTE"]

class AccountingEntry(BaseModel):
    id: str = Field(default_factory=gen_id)
    date: datetime = Field(default_factory=datetime.utcnow)
    type: EntryType = "VENTE"
    amount_cent: int = 0
    payment_method: Optional[str] = None  # CB, ESP, VIREMENT, CHQ…
    invoice_id: Optional[str] = None
    label: Optional[str] = None
