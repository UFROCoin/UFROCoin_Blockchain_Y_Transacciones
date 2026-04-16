from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from src.core.database import get_database_name, get_db_client
from src.models.block import (
    ApiErrorResponse,
    BlockValidationData,
    BlockValidationRequest,
    BlockValidationSuccessResponse,
)
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
