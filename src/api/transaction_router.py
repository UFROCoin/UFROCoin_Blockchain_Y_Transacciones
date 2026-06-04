from fastapi import APIRouter, HTTPException, Depends, Path, status
from fastapi.responses import JSONResponse
from src.models.transaction import PendingTransactionsResponse, Transaction, TransactionDetailResponse
from src.models.block import ApiErrorResponse
from src.services.transaction_service import TransactionService
from src.core.database import get_mongo_client

# --- Configuración del Router ---

router = APIRouter(
    prefix="/transactions",
    tags=["transactions"]
)

pending_router = APIRouter(
    prefix="/transaction",
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


@pending_router.get(
    "/pending",
    response_model=PendingTransactionsResponse,
    response_model_by_alias=True,  # ← agregar esto
    summary="Listar transacciones pendientes del mempool",
    description="Retorna publicamente todas las transacciones con estado PENDING que aun no han sido confirmadas en un bloque.",
)
async def get_pending_transactions(
    service: TransactionService = Depends(get_transaction_service),
):
    return {
        "status": "ok",
        "data": service.get_pending_transactions(),
    }


# ---------------------------------------------------------------------------
# GET /api/transaction/{transaction_id} — Consultar detalle de transacción
# ---------------------------------------------------------------------------


@pending_router.get(
    "/{transaction_id}",
    response_model=TransactionDetailResponse,
    response_model_by_alias=True,
    summary="Consultar detalle de una transacción por ID",
    description=(
        "Retorna todos los campos de una transacción dado su ID, incluyendo el "
        "índice del bloque en que fue confirmada (block_index) si aplica. "
        "Si la transacción aún está pendiente en el mempool, block_index será null. "
        "Este endpoint es público y no requiere autenticación."
    ),
    responses={
        status.HTTP_200_OK: {
            "description": "Transacción encontrada",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ok",
                        "data": {
                            "id": "683f1a2b3c4d5e6f7a8b9c0d",
                            "from": "a1b2c3d4e5f678901234567890abcdef12345678",
                            "to": "b1c2d3e4f5a678901234567890abcdef12345678",
                            "amount": 25.0,
                            "type": "TRANSFER",
                            "status": "CONFIRMED",
                            "timestamp": "2026-06-03T22:45:00+00:00",
                            "block_index": 3,
                        },
                    }
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ApiErrorResponse,
            "description": "No existe una transacción con el ID indicado",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "code": "TRANSACTION_NOT_FOUND",
                        "message": "Transaction not found",
                    }
                }
            },
        },
    },
)
async def get_transaction_by_id(
    transaction_id: str = Path(
        ...,
        description="ID único de la transacción a consultar (ObjectId de MongoDB).",
        examples=["683f1a2b3c4d5e6f7a8b9c0d"],
    ),
    service: TransactionService = Depends(get_transaction_service),
):
    tx = service.get_transaction_by_id(transaction_id)

    if tx is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "status": "error",
                "code": "TRANSACTION_NOT_FOUND",
                "message": "Transaction not found",
            },
        )

    return {
        "status": "ok",
        "data": tx,
    }

