from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from src.core.database import get_database_name, get_db_client
from src.models.block import (
    ApiErrorResponse,
    BlockData,
    BlockIntegrityResult,
    BlockValidationData,
    BlockValidationRequest,
    BlockValidationSuccessResponse,
    ChainSuccessResponse,
    ChainValidationData,
    ChainValidationSuccessResponse,
    TransactionResponseData,
)
from src.services.block_service import BlockService
from src.services.block_validation_service import BlockValidationService

router = APIRouter(tags=["Blockchain"])


def get_block_validation_service(db_client=Depends(get_db_client)) -> BlockValidationService:
    # Inyecta el servicio con el cliente de base de datos para futuras validaciones de cadena.
    return BlockValidationService(db_client=db_client, db_name=get_database_name())


@router.post(
    "/block/validate",
    response_model=BlockValidationSuccessResponse,
    summary="Validate block structure and hash integrity",
    description=(
        "Validates block required fields, ISO 8601 timestamp, hash formats, "
        "and deterministic SHA-256 integrity."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "model": ApiErrorResponse,
            "description": "Block structure or hash is invalid",
            "content": {
                "application/json": {
                    "example": {
                        "status": "error",
                        "code": "INVALID_BLOCK",
                        "message": "Block structure or hash is invalid",
                    }
                }
            },
        }
    },
)
async def validate_block(
    block: BlockValidationRequest,
    validation_service: BlockValidationService = Depends(get_block_validation_service),
):
    is_valid = validation_service.validate_block_integrity(block)

    if not is_valid:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "error",
                "code": "INVALID_BLOCK",
                "message": "Block structure or hash is invalid",
            },
        )

    response = BlockValidationSuccessResponse(
        status="ok",
        data=BlockValidationData(valid=True),
    )
    return response.model_dump()


# ---------------------------------------------------------------------------
# GET /api/chain — Consultar la cadena de bloques completa (US-10)
# ---------------------------------------------------------------------------


def get_block_service() -> BlockService:
    """Inyecta BlockService sin dependencia de DB explícita (usa get_blocks_collection interno)."""
    return BlockService()


@router.get(
    "/chain",
    response_model=ChainSuccessResponse,
    summary="Consultar la cadena de bloques completa",
    description=(
        "Retorna todos los bloques en orden cronológico (index ASC). "
        "No requiere autenticación — la blockchain es pública. "
        "Soporta paginación opcional con los query params page y limit."
    ),
)
async def get_chain(
    page: int = Query(default=1, ge=1, description="Página opcional para paginación"),
    limit: int = Query(default=10, ge=1, description="Cantidad de bloques por página"),
    block_service: BlockService = Depends(get_block_service),
):
    blocks_raw, _total = block_service.get_chain(page=page, limit=limit)

    blocks = [
        BlockData(
            index=b["index"],
            timestamp=b["timestamp"],
            transactions=b.get("transactions", []),
            previous_hash=b["previous_hash"],
            nonce=b["nonce"],
            hash=b["hash"],
        )
        for b in blocks_raw
    ]

    return ChainSuccessResponse(
        success=True,
        message="Blockchain retrieved successfully",
        data=blocks,
        error=None,
    ).model_dump(by_alias=True)


# ---------------------------------------------------------------------------
# GET /api/chain/validate — Validación de integridad de la cadena completa
# ---------------------------------------------------------------------------


@router.get(
    "/chain/validate",
    response_model=ChainValidationSuccessResponse,
    summary="Validar la integridad de la cadena de bloques completa",
    description=(
        "Recorre todos los bloques de la blockchain de principio a fin (index ASC), "
        "recalcula el hash SHA-256 de cada uno con los datos crudos almacenados y lo "
        "compara con el hash guardado. "
        "La operación es estrictamente read-only: no modifica ningún documento."
    ),
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "model": ApiErrorResponse,
            "description": "Error interno al acceder a la base de datos",
        }
    },
)
async def validate_chain(
    validation_service: BlockValidationService = Depends(get_block_validation_service),
):
    result = validation_service.validate_chain_integrity()

    block_results = [
        BlockIntegrityResult(
            index=b["index"],
            stored_hash=b["stored_hash"],
            computed_hash=b["computed_hash"],
            valid=b["valid"],
        )
        for b in result["blocks"]
    ]

    chain_valid: bool = result["chain_valid"]
    message = "Chain integrity verified successfully" if chain_valid else "Chain integrity compromised"

    return ChainValidationSuccessResponse(
        success=True,
        message=message,
        data=ChainValidationData(
            chain_valid=chain_valid,
            total_blocks=result["total_blocks"],
            blocks=block_results,
        ),
        error=None,
    ).model_dump()
