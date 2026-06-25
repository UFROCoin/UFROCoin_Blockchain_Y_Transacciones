"""
Router de checkpoints — endpoints de auditoría de la blockchain.

Endpoints expuestos:
  POST /api/chain/checkpoints/generate
      Genera checkpoints para todos los rangos de bloques completos que
      aún no tengan uno. Admite un cuerpo JSON opcional con ``frequency``
      para sobreescribir la frecuencia configurada por ENV.

  GET /api/chain/checkpoints
      Lista todos los checkpoints persistidos en orden ascendente de from_block.

  GET /api/chain/validate/fast
      Valida la integridad de la blockchain comparando Merkle roots actuales
      contra los checkpoints registrados. Si hay discrepancia, identifica el
      rango corrupto y el primer bloque alterado usando bisección Merkle.

Todos los endpoints son públicos (sin autenticación), en línea con la filosofía
de exposición de datos de auditoría de la cadena.
"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from src.core.database import get_blocks_collection, get_checkpoints_collection
from src.models.checkpoint import (
    CheckpointData,
    CheckpointGenerateRequest,
    CheckpointGenerateResult,
    CheckpointListResponse,
    CheckpointStatus,
    CorruptedRange,
    FastValidationResponse,
)
from src.services.checkpoint_service import CheckpointService

router = APIRouter(tags=["Checkpoints"])


# ---------------------------------------------------------------------------
# Inyección de dependencias
# ---------------------------------------------------------------------------


def get_checkpoint_service() -> CheckpointService:
    """
    Instancia CheckpointService con las colecciones MongoDB configuradas.

    No usa Depends(get_db_client) para mantener la misma convención que
    BlockService: accede directamente a las colecciones configuradas.
    """
    return CheckpointService(
        blocks_collection=get_blocks_collection(),
        checkpoints_collection=get_checkpoints_collection(),
    )


# ---------------------------------------------------------------------------
# POST /api/chain/checkpoints/generate
# ---------------------------------------------------------------------------


@router.post(
    "/chain/checkpoints/generate",
    response_model=CheckpointGenerateResult,
    summary="Generar checkpoints de la blockchain",
    description=(
        "Genera puntos de verificación (checkpoints) para todos los rangos de bloques "
        "completos que aún no tengan uno. "
        "La frecuencia por defecto se toma de la variable de entorno CHECKPOINT_FREQUENCY "
        "(valor por defecto: 100 bloques). "
        "Se puede sobreescribir enviando el campo `frequency` en el cuerpo de la petición. "
        "Los rangos con checkpoint existente se omiten (no se duplican). "
        "Si el cálculo del Merkle root falla para un rango, ese rango no se persiste. "
        "La operación no modifica bloques, transacciones ni saldos."
    ),
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Error interno al acceder a la base de datos.",
        }
    },
)
async def generate_checkpoints(
    body: CheckpointGenerateRequest | None = None,
    service: CheckpointService = Depends(get_checkpoint_service),
) -> dict:
    frequency = body.frequency if body is not None else None
    result = service.generate_checkpoints(frequency=frequency)

    checkpoints_data = [
        CheckpointData(
            from_block=cp["from_block"],
            to_block=cp["to_block"],
            merkle_root=cp["merkle_root"],
            last_block_hash=cp["last_block_hash"],
            created_at=cp["created_at"],
            status=CheckpointStatus(cp["status"]),
        )
        for cp in result["data"]
    ]

    return CheckpointGenerateResult(
        status="ok",
        generated=result["generated"],
        skipped=result["skipped"],
        errors=result["errors"],
        data=checkpoints_data,
    ).model_dump()


# ---------------------------------------------------------------------------
# GET /api/chain/checkpoints
# ---------------------------------------------------------------------------


@router.get(
    "/chain/checkpoints",
    response_model=CheckpointListResponse,
    summary="Listar checkpoints de la blockchain",
    description=(
        "Retorna todos los checkpoints persistidos, ordenados de forma ascendente "
        "por el índice del primer bloque del rango (from_block). "
        "Si no hay checkpoints, retorna una lista vacía. "
        "Endpoint público — no requiere autenticación."
    ),
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Error interno al acceder a la base de datos.",
        }
    },
)
async def list_checkpoints(
    service: CheckpointService = Depends(get_checkpoint_service),
) -> dict:
    checkpoints_raw = service.list_checkpoints()

    checkpoints_data = [
        CheckpointData(
            from_block=cp["from_block"],
            to_block=cp["to_block"],
            merkle_root=cp["merkle_root"],
            last_block_hash=cp["last_block_hash"],
            created_at=cp["created_at"],
            status=CheckpointStatus(cp["status"]),
        )
        for cp in checkpoints_raw
    ]

    return CheckpointListResponse(
        status="ok",
        data=checkpoints_data,
    ).model_dump()


# ---------------------------------------------------------------------------
# GET /api/chain/validate/fast
# ---------------------------------------------------------------------------


@router.get(
    "/chain/validate/fast",
    response_model=FastValidationResponse,
    summary="Validación rápida de la blockchain usando checkpoints y árbol Merkle",
    description=(
        "Valida la integridad de la blockchain comparando los Merkle roots actuales "
        "contra los checkpoints registrados, sin recorrer toda la cadena bloque a bloque. "
        "Si no existen checkpoints, retorna valid=false con reason=CHECKPOINTS_NOT_FOUND. "
        "Cuando se detecta una discrepancia de Merkle root, identifica el rango corrupto "
        "y usa bisección sobre el árbol de hashes para localizar el primer bloque alterado. "
        "La operación es estrictamente read-only: no modifica bloques, transacciones ni saldos. "
        "Endpoint público — no requiere autenticación."
    ),
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Error interno al acceder a la base de datos.",
        }
    },
)
async def validate_fast(
    service: CheckpointService = Depends(get_checkpoint_service),
) -> dict:
    result = service.validate_fast()

    corrupted_range = None
    if result["corrupted_range"] is not None:
        corrupted_range = CorruptedRange(
            from_block=result["corrupted_range"]["from_block"],
            to_block=result["corrupted_range"]["to_block"],
        )

    return FastValidationResponse(
        valid=result["valid"],
        message=result.get("message"),
        reason=result.get("reason"),
        corrupted_range=corrupted_range,
        first_corrupted_block=result.get("first_corrupted_block"),
        expected_root=result.get("expected_root"),
        actual_root=result.get("actual_root"),
    ).model_dump()
