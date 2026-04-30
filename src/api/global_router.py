from fastapi import APIRouter

from src.api.history_router import router as history_router

router = APIRouter(tags=["global"])


@router.get(
    "/health",
    summary="Verificar estado de la API",
    description="Confirma que el servicio esta disponible y respondiendo correctamente.",
    responses={200: {"description": "Servicio operativo"}},
)
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}

# --- Registro de Enrutadores ---

router.include_router(history_router)