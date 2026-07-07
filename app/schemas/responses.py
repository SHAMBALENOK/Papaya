from pydantic import BaseModel
from app.schemas.token import TokenResponse
from typing import Optional

class APIResponse(BaseModel):
    code: int
    hint: str