from pydantic import BaseModel, EmailStr, Field
from .common import gen_id

class Address(BaseModel):
    line1: str
    line2: str | None = None
    postal_code: str
    city: str

class Client(BaseModel):
    id: str = Field(default_factory=gen_id)
    name: str
    contact_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: Address | None = None
    notes: str | None = None
