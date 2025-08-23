from pydantic import BaseModel, Field
from .common import gen_id

class Product(BaseModel):
    id: str = Field(default_factory=gen_id)
    type: str = "product"
    ref: str
    label: str
    description: str | None = None
    price_ttc_cent: int
    unit: str = "pièce"
    active: bool = True
