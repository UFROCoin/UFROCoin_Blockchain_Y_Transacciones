from fastapi import APIRouter, Depends, HTTPException, status
from src.core.security import verify_wallet_owner
from src.services.history_service import get_wallet_history

# --- Configuracion del Router ---

router = APIRouter(prefix="/history", tags=["history"])

# --- Endpoints ---

@router.get(
    "/{address}",
    summary="Obtener historial de movimientos",
    description="Retorna el listado cronológico de transacciones asociadas a una wallet. Incluye transacciones confirmadas (en la blockchain) y pendientes (en el mempool). Requiere que el token JWT pertenezca al dueño de la wallet consultada."
)
def get_history(address: str, verified_address: str = Depends(verify_wallet_owner)):
    try:
        return get_wallet_history(verified_address)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )