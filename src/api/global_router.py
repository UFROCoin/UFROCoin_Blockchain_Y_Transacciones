from fastapi import APIRouter


router = APIRouter(tags=["global"])


@router.get(
    "/health",
    summary="Verificar estado de la API",
    description="Confirma que el servicio esta disponible y respondiendo correctamente.",
    responses={200: {"description": "Servicio operativo"}},
)
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
