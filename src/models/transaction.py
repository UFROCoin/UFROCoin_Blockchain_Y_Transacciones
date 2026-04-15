from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

# --- Enumeraciones ---

class TransactionType(str, Enum):
    TRANSFER = "TRANSFER"
    GENESIS = "GENESIS"
    MINING_REWARD = "MINING_REWARD"

class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"

# --- Modelos de Datos ---

class Transaction(BaseModel):
    sender: str = Field(..., alias="from")
    receiver: str = Field(..., alias="to")
    amount: float = Field(..., gt=0)
    type: TransactionType = TransactionType.TRANSFER
    status: TransactionStatus = TransactionStatus.PENDING
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    block_index: Optional[int] = None

    model_config = ConfigDict(populate_by_name=True)