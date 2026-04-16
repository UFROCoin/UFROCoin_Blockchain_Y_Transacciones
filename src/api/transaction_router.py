from fastapi import APIRouter, HTTPException, Depends
from src.models.transaction import Transaction
from src.services.transaction_service import TransactionService
from src.core.database import get_mongo_client

# --- Configuración del Router ---

router = APIRouter(
    prefix="/transactions",
    tags=["transactions"]
)

# --- Inyección de Dependencias ---

def get_transaction_service():
    return TransactionService(get_mongo_client())

# --- Endpoints ---

@router.post("/", response_model=Transaction)
async def create_transaction(
    transaction: Transaction, 
    service: TransactionService = Depends(get_transaction_service)
):
    try:
        new_tx = service.create_transfer(transaction.model_dump(by_alias=True))
        return new_tx
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
