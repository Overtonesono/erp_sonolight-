from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Literal, Optional
from datetime import datetime
from .common import gen_id

QuoteStatus = Literal["DRAFT", "SENT", "ACCEPTED", "REFUSED"]

class QuoteLine(BaseModel):
    item_id: Optional[str] = None
    item_type: Literal["product", "service"] = "service"
    label: str
    qty: float = 1.0
    unit_price_ttc_cent: int = 0
    remise_pct: float = 0.0  # 0..100
    total_line_ttc_cent: int = 0  # calculé et stocké pour snapshot

class Quote(BaseModel):
    id: str = Field(default_factory=gen_id)
    number: Optional[str] = None
    client_id: str
    status: QuoteStatus = "DRAFT"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None

    lines: List[QuoteLine] = Field(default_factory=list)
    total_ttc_cent: int = 0
    notes: Optional[str] = None
