from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime
from .common import gen_id

InvoiceType = Literal["ACOMPTE", "SOLDE", "FINALE"]
InvoiceStatus = Literal["DRAFT", "ISSUED", "PAID"]

class InvoiceLine(BaseModel):
    label: str
    qty: float = 1.0
    unit_price_ttc_cent: int = 0
    total_line_ttc_cent: int = 0  # snapshot, TTC, pas de TVA

class Invoice(BaseModel):
    id: str = Field(default_factory=gen_id)
    number: Optional[str] = None
    type: InvoiceType = "ACOMPTE"
    status: InvoiceStatus = "DRAFT"

    quote_id: str
    client_id: str

    lines: List[InvoiceLine] = Field(default_factory=list)
    total_ttc_cent: int = 0

    created_at: datetime = Field(default_factory=datetime.utcnow)
    issued_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None

    notes: Optional[str] = None
