from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CheckpointStatus(str, Enum):
    """Estado de un checkpoint tras su generación."""

    CREATED = "CREATED"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Documento interno (refleja el documento MongoDB)
# ---------------------------------------------------------------------------


class CheckpointDocument(BaseModel):
    """Representa un documento de checkpoint tal como se almacena en MongoDB."""

    model_config = ConfigDict(extra="ignore")

    from_block: int = Field(
        ...,
        ge=0,
        description="Índice del primer bloque del rango cubierto por este checkpoint.",
        examples=[0],
    )
    to_block: int = Field(
        ...,
        ge=0,
        description="Índice del último bloque del rango cubierto por este checkpoint.",
        examples=[99],
    )
    merkle_root: str = Field(
        ...,
        description="Merkle root SHA-256 calculado sobre los hashes de los bloques del rango.",
        examples=["a3f1..."],
    )
    last_block_hash: str = Field(
        ...,
        description="Hash SHA-256 del último bloque incluido en el checkpoint.",
        examples=["7e2c..."],
    )
    created_at: str = Field(
        ...,
        description="Fecha-hora ISO 8601 (UTC) de creación del checkpoint.",
        examples=["2026-06-25T06:00:00Z"],
    )
    status: CheckpointStatus = Field(
        ...,
        description="Estado del checkpoint: CREATED si fue generado correctamente.",
        examples=["CREATED"],
    )


# ---------------------------------------------------------------------------
# Payload público (respuesta de la API)
# ---------------------------------------------------------------------------


class CheckpointData(BaseModel):
    """Payload de un checkpoint serializado en la respuesta pública de la API."""

    model_config = ConfigDict(extra="forbid")

    from_block: int = Field(
        ...,
        ge=0,
        description="Índice del primer bloque del rango.",
        examples=[0],
    )
    to_block: int = Field(
        ...,
        ge=0,
        description="Índice del último bloque del rango.",
        examples=[99],
    )
    merkle_root: str = Field(
        ...,
        description="Merkle root SHA-256 del rango de bloques.",
        examples=["a3f1..."],
    )
    last_block_hash: str = Field(
        ...,
        description="Hash SHA-256 del último bloque del rango.",
        examples=["7e2c..."],
    )
    created_at: str = Field(
        ...,
        description="Fecha-hora ISO 8601 (UTC) de creación del checkpoint.",
        examples=["2026-06-25T06:00:00Z"],
    )
    status: CheckpointStatus = Field(
        ...,
        description="Estado del checkpoint.",
        examples=["CREATED"],
    )


# ---------------------------------------------------------------------------
# Respuesta — checkpoint individual
# ---------------------------------------------------------------------------


class CheckpointResponse(BaseModel):
    """Envelope estándar para un solo checkpoint generado."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = Field(
        ...,
        description="Estado de la solicitud.",
        examples=["ok"],
    )
    data: CheckpointData = Field(
        ...,
        description="Datos del checkpoint generado.",
    )


# ---------------------------------------------------------------------------
# Respuesta — lista de checkpoints
# ---------------------------------------------------------------------------


class CheckpointListResponse(BaseModel):
    """Envelope estándar para una lista de checkpoints."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = Field(
        ...,
        description="Estado de la solicitud.",
        examples=["ok"],
    )
    data: list[CheckpointData] = Field(
        ...,
        description="Lista de checkpoints en orden ascendente de from_block.",
    )


# ---------------------------------------------------------------------------
# Respuesta — resultado de generación (puede incluir múltiples checkpoints)
# ---------------------------------------------------------------------------


class CheckpointGenerateResult(BaseModel):
    """Resultado completo de una operación de generación de checkpoints."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"] = Field(
        ...,
        description="Estado de la solicitud.",
        examples=["ok"],
    )
    generated: int = Field(
        ...,
        ge=0,
        description="Cantidad de checkpoints nuevos persistidos en esta ejecución.",
        examples=[2],
    )
    skipped: int = Field(
        ...,
        ge=0,
        description="Cantidad de rangos omitidos porque ya existía un checkpoint.",
        examples=[1],
    )
    errors: int = Field(
        ...,
        ge=0,
        description=(
            "Cantidad de rangos donde el cálculo del Merkle tree falló. "
            "Estos rangos no se persistieron."
        ),
        examples=[0],
    )
    data: list[CheckpointData] = Field(
        ...,
        description="Lista de los checkpoints generados en esta ejecución.",
    )


# ---------------------------------------------------------------------------
# Cuerpo de la petición POST /api/chain/checkpoints/generate
# ---------------------------------------------------------------------------


class CheckpointGenerateRequest(BaseModel):
    """
    Cuerpo opcional de la petición de generación de checkpoints.

    Si no se proporciona `frequency`, se utiliza el valor configurado
    en la variable de entorno CHECKPOINT_FREQUENCY (default 100).
    """

    model_config = ConfigDict(extra="forbid")

    frequency: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Frecuencia de generación de checkpoints expresada en cantidad de bloques. "
            "Valores típicos: 50, 100, 1000. "
            "Si se omite, se usa la variable de entorno CHECKPOINT_FREQUENCY."
        ),
        examples=[100],
    )


# ---------------------------------------------------------------------------
# Modelos para GET /api/chain/validate/fast
# ---------------------------------------------------------------------------


class CorruptedRange(BaseModel):
    """Rango de bloques donde se detectó una discrepancia de Merkle root."""

    model_config = ConfigDict(extra="forbid")

    from_block: int = Field(
        ...,
        ge=0,
        description="Índice del primer bloque del rango corrupto.",
        examples=[301],
    )
    to_block: int = Field(
        ...,
        ge=0,
        description="Índice del último bloque del rango corrupto.",
        examples=[400],
    )


class FastValidationResponse(BaseModel):
    """
    Respuesta del endpoint GET /api/chain/validate/fast.

    Cubre tres escenarios en un único modelo con campos opcionales:

    1. Cadena íntegra:
       valid=True, message="...", resto None.

    2. Corrupción detectada:
       valid=False, corrupted_range={...}, first_corrupted_block=N,
       expected_root="...", actual_root="...", reason="MERKLE_ROOT_MISMATCH".

    3. Sin checkpoints:
       valid=False, reason="CHECKPOINTS_NOT_FOUND", resto None.
    """

    model_config = ConfigDict(extra="forbid")

    valid: bool = Field(
        ...,
        description="True si la validación rápida no encontró discrepancias.",
        examples=[True],
    )
    message: str | None = Field(
        default=None,
        description="Mensaje descriptivo cuando valid=True.",
        examples=["Blockchain integrity verified using checkpoints and hash tree"],
    )
    reason: str | None = Field(
        default=None,
        description=(
            "Código de razón del fallo cuando valid=False. "
            "Valores posibles: MERKLE_ROOT_MISMATCH, CHECKPOINTS_NOT_FOUND."
        ),
        examples=["MERKLE_ROOT_MISMATCH"],
    )
    corrupted_range: CorruptedRange | None = Field(
        default=None,
        description="Rango donde se detectó la discrepancia de Merkle root.",
    )
    first_corrupted_block: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Índice del primer bloque alterado encontrado dentro del rango corrupto. "
            "None si no se pudo identificar un bloque específico."
        ),
        examples=[347],
    )
    expected_root: str | None = Field(
        default=None,
        description="Merkle root registrado en el checkpoint (valor esperado).",
        examples=["abc123..."],
    )
    actual_root: str | None = Field(
        default=None,
        description="Merkle root recalculado sobre los hashes actuales de los bloques.",
        examples=["def456..."],
    )

