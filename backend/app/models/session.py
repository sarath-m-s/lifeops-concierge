from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AuthSession(BaseModel):
    user_id: str
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: datetime
    is_mock: bool = True
