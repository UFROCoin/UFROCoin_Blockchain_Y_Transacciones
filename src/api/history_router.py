from typing import List
from fastapi import APIRouter, Depends, status

from src.core.security import verify_wallet_owner
from src.models.history import TransactionHistoryItem
from src.services.transaction_service import TransactionService
from src.core.database import get_db_client

# --- Configuración del Router ---

router = APIRouter(
    prefix="/history",
    tags=["History"]
)

# --- Inyección de Dependencias ---

def get_transaction_service(db_client=Depends(get_db_client)) -> TransactionService:
    return TransactionService(db_client)

# --- Endpoints ---

@router.get(
    "/{address}", 
    response_model=List[TransactionHistoryItem],
    summary="Obtener historial de movimientos",
    description=(
        "Retorna el listado cronológico de transacciones asociadas a una wallet. "
        "Incluye transacciones confirmadas (en la blockchain) y pendientes (en el mempool). "
        "Requiere que el token JWT pertenezca al dueño de la wallet consultada."
    ),
    responses={
        200: {
            "description": "Lista de transacciones obtenida exitosamente.",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "_id": "651f...",
                            "type": "SEND",
                            "from": "0xABC...",
                            "to": "0xXYZ...",
                            "amount": 10.5,
                            "timestamp": "2023-10-27T10:00:00Z",
                            "status": "CONFIRMED"
                        }
                    ]
                }
            }
        },
        401: {"description": "No autenticado o token inválido."},
        403: {"description": "Acceso denegado: La wallet no pertenece al usuario del token."},
    }
)
def get_transaction_history(
    address: str,
    owner_address: str = Depends(verify_wallet_owner),
    service: TransactionService = Depends(get_transaction_service)
):
    """
    Llamada al servicio para obtener el historial unificado.
    """
    history_data = service.get_transaction_history(address)
    return history_data