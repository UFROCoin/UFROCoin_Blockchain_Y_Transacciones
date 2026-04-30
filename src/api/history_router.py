from typing import Listfrom 
from fastapi import APIRouter, Depends

from src.core.security import verify_wallet_owner
from src.models.history import TransactionHistoryItem
from src.services.transaction_service import TransactionService
from src.core.database import get_db_client

# --- Configuración del Router --- 

router = APIRouter(
    prefix="/history",
    tags=["History"]
)

# --- Inyección de Dependencias

def get_transaction_service(db_client=Depends(get_db_client)) -> TransactionService:
    return TransactionService(db_client)

# --- Endpoints ---

@router.get("/{address}", response_model=List[TransactionHistoryItem])
def get_transaction_history(
    address: str,
    owner_address: str = Depends(verify_wallet_owner),
    service: TransactionService = Depends(get_transaction_service)
):
    history_data = service.get_transaction_history(address)
    return history_data