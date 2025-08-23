from pydantic import BaseModel, Field
from datetime import datetime
import uuid

def gen_id() -> str:
    return str(uuid.uuid4())

class TimeStamped(BaseModel):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def touch(self):
        object.__setattr__(self, "updated_at", datetime.utcnow())
