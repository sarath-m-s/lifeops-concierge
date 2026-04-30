from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class UserPreferences(BaseModel):
    cuisine_prefs: List[str] = []
    dietary_notes: List[str] = []
    budget_range: Optional[str] = None
    household_staples: List[str] = []
    voice_enabled: bool = True
    consent_timestamp: Optional[datetime] = None
