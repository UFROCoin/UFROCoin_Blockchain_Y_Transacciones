from pydantic import BaseModel, Field
from typing import Optional

class TransactionHistoryItem(BaseModel):
    id: str = Field(..., alias="_id")
    type: str  # SEND, RECEIVE, MINING_REWARD, GENESIS
    from_address: Optional[str] = Field(None, alias="from")
    to_address: str = Field(..., alias="to")
    amount: float
    timestamp: str
    status: str # PENDING, CONFIRMED

    class Config:
        populate_by_name = True