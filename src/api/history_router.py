from fastapi import APIRouter, Depends, HTTPException, status, Query
from src.core.security import verify_wallet_owner
from src.services.history_service import get_wallet_history

# --- Configuracion del Router ---

router = APIRouter(prefix="/history", tags=["history"])

# --- Endpoints ---

@router.get(
    "/{address}",
    response_model=list[dict],
    summary="Obtener historial de movimientos",
    description="Retorna el listado cronológico de transacciones asociadas a una wallet. Incluye transacciones confirmadas y pendientes. Soporta paginación."
)
def get_history(
    address: str,
    page: int = Query(1, ge=1, description="Numero de pagina (comienza en 1)"),
    limit: int = Query(10, ge=1, le=100, description="Cantidad de registros por pagina"),
    verified_address: str = Depends(verify_wallet_owner)
):
    try:
        return get_wallet_history(verified_address, page, limit)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )