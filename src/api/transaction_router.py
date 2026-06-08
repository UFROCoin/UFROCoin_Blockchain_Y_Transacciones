from fastapi import APIRouter, HTTPException, Depends, status
from src.models.transaction import PendingTransactionsResponse, Transaction
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
    description=(
        "Registra una transferencia en el mempool tras aplicar las siguientes validaciones de seguridad:\n"
        "- El monto debe ser estrictamente positivo con un máximo de 2 decimales.\n"
        "- Ambas wallets (origen y destino) deben existir en el sistema.\n"
        "- El emisor no puede superar un límite máximo de 10 transacciones pendientes simultáneas."
    ),
    responses={
        400: {
            "description": "Error de validación de seguridad",
            "content": {
                "application/json": {
                    "examples": {
                        "monto_invalido": {
                            "summary": "Monto menor o igual a cero",
                            "value": {"detail": "INVALID_AMOUNT"}
                        },
                        "decimales_excedidos": {
                            "summary": "Más de 2 decimales",
                            "value": {"detail": "El monto no puede tener más de 2 decimales"}
                        },
                        "wallet_origen_inexistente": {
                            "summary": "Wallet de origen no encontrada",
                            "value": {"detail": "La wallet de origen es invalida o no existe"}
                        },
                        "wallet_destino_inexistente": {
                            "summary": "Wallet de destino no encontrada",
                            "value": {"detail": "La wallet de destino es invalida o no existe"}
                        },
                        "limite_mempool_excedido": {
                            "summary": "Límite anti-spam superado",
                            "value": {"detail": "PENDING_LIMIT_EXCEEDED"}
                        },
                        "saldo_insuficiente": {
                            "summary": "Fondos insuficientes",
                            "value": {"detail": "Saldo insuficiente. Saldo disponible: X.X"}
                        }
                    }
                }
            }
        },
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
        import traceback
        traceback.print_exc() 
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"DETALLE DEL ERROR: {str(e)}"
        )


@router.get(
    "/pending",
    response_model=PendingTransactionsResponse,
    response_model_by_alias=True,
    summary="Listar transacciones pendientes del mempool",
    description="Retorna públicamente todas las transacciones con estado PENDING que aún no han sido confirmadas en un bloque.",
)
async def get_pending_transactions(
    service: TransactionService = Depends(get_transaction_service),
):
    return {
        "status": "ok",
        "data": service.get_pending_transactions(),
    }