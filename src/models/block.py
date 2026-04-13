from typing import Any

from pydantic import BaseModel, Field


class BlockValidationRequest(BaseModel):
    index: int = Field(
        ...,
        description="Block position in the chain.",
        examples=[1],
    )
    timestamp: str = Field(
        ...,
        description="Block creation date-time in ISO 8601 format.",
        examples=["2026-04-13T18:45:00Z"],
    )
    transactions: list[dict[str, Any]] = Field(
        ...,
        description="Transactions included in the block.",
        examples=[[
            {
                "from": "a1b2c3d4e5f678901234567890abcdef12345678",
                "to": "b1c2d3e4f5a678901234567890abcdef12345678",
                "amount": 25.0,
                "type": "TRANSFER",
            }
        ]],
    )
    previous_hash: str = Field(
        ...,
        description="SHA-256 hash of the previous block.",
        examples=["0f7a9e3c5e7a1205f8c31f5b8d21ca74095e78eb1ec6dced3d4f8a05d8e6c712"],
    )
    nonce: int = Field(
        ...,
        description="Proof of Work nonce used to mine the block.",
        examples=[48271],
    )
    hash: str = Field(
        ...,
        description="SHA-256 hash of the current block.",
        examples=["18f5fd2362deb9c68af6147334c6f66d2b816af67efea6460040b605d774aeb4"],
    )
