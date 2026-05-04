from fastapi import APIRouter, HTTPException, Depends, status
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

@router.post(
    "/", 
    response_model=Transaction,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nueva transferencia",
    description="Registra una transferencia en el mempool tras validar que la wallet de destino existe y que el emisor tiene saldo suficiente.",
    responses={
        400: {"description": "Error de validación: Saldo insuficiente o wallet de destino no encontrada"},
        500: {"description": "Error interno del servidor"}
    }
)
async def create_transaction(
    transaction: Transaction, 
    service: TransactionService = Depends(get_transaction_service)
):
    try:
        new_tx = service.create_transfer(transaction.model_dump(by_alias=True))
        return new_tx
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=str(ve)
        )
    except Exception as e:
        # Vamos a imprimir el error en consola y enviarlo en la respuesta
        import traceback
        traceback.print_exc() 
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"DETALLE DEL ERROR: {str(e)}"
        )