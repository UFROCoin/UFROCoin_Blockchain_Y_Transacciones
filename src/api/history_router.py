from fastapi import APIRouter, Depends, HTTPException, status
from src.core.security import verify_wallet_owner
from src.services.history_service import get_wallet_history

# --- Configuración del Router ---

router = APIRouter(prefix="/history", tags=["history"])

# --- Endpoints ---

@router.get(
    "/{address}",
    response_model=list[dict],
    summary="Obtener historial de movimientos",
    description="Retorna el listado cronológico de transacciones asociadas a una wallet. Incluye transacciones confirmadas y pendientes."
)
def get_history(address: str, verified_address: str = Depends(verify_wallet_owner)):
    try:
        return get_wallet_history(verified_address)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )