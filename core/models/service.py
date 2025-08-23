from pydantic import BaseModel, Field
from .common import gen_id

class Service(BaseModel):
    id: str = Field(default_factory=gen_id)
    type: str = "service"
    ref: str
    label: str
    description: str | None = None
    price_ttc_cent: int
    unit: str = "prestation"
    active: bool = True
