from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
from typing import Literal, Optional
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


class PendingTransactionData(BaseModel):
    id: str
    sender: str = Field(..., alias="from")
    receiver: str = Field(..., alias="to")
    amount: float
    timestamp: str

    model_config = ConfigDict(populate_by_name=True)


class TransactionDetail(BaseModel):
    """Detalle completo de una transacción individual."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(
        ...,
        description="Identificador único de la transacción (ObjectId de MongoDB).",
        examples=["683f1a2b3c4d5e6f7a8b9c0d"],
    )
    sender: str = Field(
        ...,
        alias="from",
        description="Dirección de la wallet de origen.",
        examples=["a1b2c3d4e5f678901234567890abcdef12345678"],
    )
    receiver: str = Field(
        ...,
        alias="to",
        description="Dirección de la wallet de destino.",
        examples=["b1c2d3e4f5a678901234567890abcdef12345678"],
    )
    amount: float = Field(
        ...,
        description="Monto transferido en UFROCoin.",
        examples=[25.0],
    )
    type: str = Field(
        ...,
        description="Tipo de transacción (TRANSFER, GENESIS, MINING_REWARD).",
        examples=["TRANSFER"],
    )
    status: str = Field(
        ...,
        description="Estado de la transacción (PENDING o CONFIRMED).",
        examples=["CONFIRMED"],
    )
    timestamp: str = Field(
        ...,
        description="Fecha-hora ISO 8601 de creación de la transacción.",
        examples=["2026-06-03T22:45:00+00:00"],
    )
    block_index: Optional[int] = Field(
        default=None,
        ge=0,
        description="Índice del bloque en que fue confirmada la transacción. null si aún está pendiente.",
        examples=[3],
    )


class TransactionDetailResponse(BaseModel):
    """Respuesta estándar del endpoint GET /api/transactions/{id}."""

    status: Literal["ok"] = Field(
        ...,
        description="Estado de la solicitud.",
        examples=["ok"],
    )
    data: TransactionDetail = Field(
        ...,
        description="Detalle completo de la transacción consultada.",
    )


class PendingTransactionsResponse(BaseModel):
    status: Literal["ok"]
    data: list[PendingTransactionData]
