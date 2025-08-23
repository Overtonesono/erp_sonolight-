from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from .common import gen_id


class Product(BaseModel):
  id: str = Field(default_factory=gen_id)
  ref: str
  label: str
  price_ttc_cent: int = 0
  unit: str = "unité"
  active: bool = True
  # ✨ Nouveau
  description: Optional[str] = None
