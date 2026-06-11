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
    ChainStatsData,
    ChainStatsResponse,
    ChainSuccessResponse,
    ChainValidateResponse,
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


def block_not_found_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "status": "error",
            "code": "BLOCK_NOT_FOUND",
            "message": "Block not found",
        },
    )


@router.get(
    "/block/hash/{block_hash}",
    response_model=BlockData,
    summary="Consultar bloque por hash",
    description="Retorna un bloque específico por su hash e incluye todas sus transacciones.",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ApiErrorResponse,
            "description": "No existe un bloque con el hash indicado",
        }
    },
)
async def get_block_by_hash(
    block_hash: str,
    block_service: BlockService = Depends(get_block_service),
):
    block = block_service.get_block_by_hash(block_hash)
    if block is None:
        return block_not_found_response()

    return BlockData(
        index=block["index"],
        timestamp=block["timestamp"],
        transactions=block.get("transactions", []),
        previous_hash=block["previous_hash"],
        nonce=block["nonce"],
        hash=block["hash"],
    ).model_dump(by_alias=True)


@router.get(
    "/block/{index}",
    response_model=BlockData,
    summary="Consultar bloque por índice",
    description="Retorna un bloque específico por índice e incluye todas sus transacciones.",
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ApiErrorResponse,
            "description": "No existe un bloque con el índice indicado",
        }
    },
)
async def get_block_by_index(
    index: int,
    block_service: BlockService = Depends(get_block_service),
):
    block = block_service.get_block_by_index(index)
    if block is None:
        return block_not_found_response()

    return BlockData(
        index=block["index"],
        timestamp=block["timestamp"],
        transactions=block.get("transactions", []),
        previous_hash=block["previous_hash"],
        nonce=block["nonce"],
        hash=block["hash"],
    ).model_dump(by_alias=True)


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
# GET /api/chain/stats — Estadísticas en tiempo real de la cadena (US)
# ---------------------------------------------------------------------------


@router.get(
    "/chain/stats",
    response_model=ChainStatsResponse,
    summary="Estadísticas en tiempo real de la cadena de bloques",
    description=(
        "Recorre toda la blockchain y retorna el número total de bloques, "
        "el timestamp del último bloque, la cantidad total de transacciones "
        "y la suma total de UFROCoins emitidos. "
        "Endpoint público — no requiere JWT."
    ),
)
async def get_chain_stats(
    block_service: BlockService = Depends(get_block_service),
):
    stats = block_service.get_chain_stats()

    return ChainStatsResponse(
        status="ok",
        data=ChainStatsData(
            total_blocks=stats["total_blocks"],
            last_block_time=stats["last_block_time"],
            total_transactions=stats["total_transactions"],
            total_ufrocoins_emitidos=stats["total_ufrocoins_emitidos"],
        ),
    ).model_dump()


# ---------------------------------------------------------------------------
# GET /api/chain/validate — Validación de integridad de la cadena completa
# ---------------------------------------------------------------------------


@router.get(
    "/chain/validate",
    response_model=ChainValidateResponse,
    summary="Validar la integridad de la cadena de bloques completa",
    description=(
        "Recorre todos los bloques de la blockchain de principio a fin (index ASC), "
        "recalcula el hash SHA-256 de cada uno con los datos crudos almacenados y lo "
        "compara con el hash guardado. Además verifica que el previous_hash de cada "
        "bloque coincida con el hash del bloque anterior (continuidad de la cadena). "
        "La operación es estrictamente read-only: no modifica ningún documento. "
        "Si la cadena es inválida, se genera un log en el servidor con el índice "
        "del primer bloque corrupto detectado."
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

    return ChainValidateResponse(
        valid=result["chain_valid"],
        error_at_block=result["error_at_block"],
    ).model_dump()
